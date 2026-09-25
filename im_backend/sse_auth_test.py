"""Cookie SSE auth contract; no external services or model calls."""
import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from im_backend.api.auth_router import router
from im_backend.api.core import get_auth_service, get_current_user, get_sse_user
from im_backend.application.auth_service import AuthService


class Store:
    def __init__(self):
        self.rows = {}

    def find_one(self, collection, query):
        return next((r for r in self.rows.get(collection, []) if all(r.get(k) == v for k, v in query.items())), None)

    def insert_one(self, collection, item):
        self.rows.setdefault(collection, []).append(item)
        return item

    def update_one(self, collection, query, update):
        self.find_one(collection, query).update(update)


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv('IM_SSE_COOKIE_SECURE', 'false')
    store = Store()
    auth = AuthService(store)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_service] = lambda: auth

    @app.get('/api/im/test/events')
    def events(user=Depends(get_sse_user)):
        return user

    @app.post('/api/im/test/write')
    def write(user=Depends(get_current_user)):
        return user

    with TestClient(app, base_url='http://testserver') as client:
        yield client, store


def register(client):
    response = client.post('/api/im/auth/register', json={
        'username': 'sse-user', 'email': 'sse@example.test', 'password': 'test-password',
    })
    assert response.status_code == 200
    return response


def test_cookie_attributes_and_bearer_only_ordinary_api(auth_client):
    client, store = auth_client
    response = register(client)
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Path=/api/im' in cookie
    assert 'Domain=' not in cookie and 'Secure' not in cookie
    assert client.get('/api/im/test/events').status_code == 200
    assert client.get('/api/im/auth/me').status_code == 401
    assert client.post('/api/im/test/write').status_code == 401
    token = response.json()['item']['token']
    assert client.post('/api/im/test/write', headers={'Authorization': 'Bearer ' + token}).status_code == 200
    for invalid in ('Bearer invalid', 'Basic abc', 'Bearer', ''):
        assert client.get('/api/im/test/events', headers={'Authorization': invalid}).status_code == 401


def test_restore_cookie_ttl_revocation_and_logout(auth_client):
    client, store = auth_client
    token = register(client).json()['item']['token']
    headers = {'Authorization': 'Bearer ' + token}
    client.cookies.clear()
    assert client.get('/api/im/test/events').status_code == 401
    record = store.find_one('im_sessions', {'token': token})
    record['expires_at'] = time.time() + 120
    response = client.get('/api/im/auth/me', headers=headers)
    assert client.cookies.get('im_sse_session') == token
    max_age = int(response.headers['set-cookie'].split('Max-Age=')[1].split(';')[0])
    assert 0 < max_age <= 120
    assert client.get('/api/im/test/events').status_code == 200
    response = client.post('/api/im/auth/logout', headers=headers)
    assert response.status_code == 200 and 'Max-Age=0' in response.headers['set-cookie']
    assert client.get('/api/im/test/events', headers={'Cookie': 'im_sse_session=' + token}).status_code == 401
    assert client.get('/api/im/auth/me', headers=headers).status_code == 401


def test_expired_session_and_same_origin_cookie_only(auth_client):
    client, store = auth_client
    token = register(client).json()['item']['token']
    assert client.get('/api/im/test/events', headers={'Origin': 'http://testserver'}).status_code == 200
    for headers in ({'Origin': 'https://other.test'}, {'Sec-Fetch-Site': 'same-site'}, {'Sec-Fetch-Site': 'cross-site'}):
        assert client.get('/api/im/test/events', headers=headers).status_code == 403
    # Explicit Bearer retains the existing non-cookie access contract.
    assert client.get('/api/im/test/events', headers={
        'Origin': 'https://other.test', 'Authorization': 'Bearer ' + token,
    }).status_code == 200
    store.find_one('im_sessions', {'token': token})['expires_at'] = time.time() - 1
    assert client.get('/api/im/test/events').status_code == 401


def test_login_sets_cookie_and_secure_is_default(auth_client, monkeypatch):
    client, _ = auth_client
    register(client)
    monkeypatch.delenv('IM_SSE_COOKIE_SECURE')
    response = client.post('/api/im/auth/login', json={'username': 'sse-user', 'password': 'test-password'})
    assert response.status_code == 200
    assert 'Secure' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'no-store'
