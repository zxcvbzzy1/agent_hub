from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any


class AuthError(Exception):
    pass


class DuplicateUserError(ValueError):
    pass


class AuthService:
    def __init__(self, store, session_ttl_seconds: int = 7 * 24 * 60 * 60) -> None:
        self._store = store
        self._session_ttl_seconds = session_ttl_seconds

    def register(
        self,
        *,
        username: str,
        email: str,
        password: str,
        display_name: str = "",
        avatar_url: str = "",
    ) -> dict[str, Any]:
        username = username.strip()
        email = email.strip().lower()
        self._validate_credentials(username=username, email=email, password=password)
        if self._store.find_one("im_users", {"username": username}) is not None:
            raise DuplicateUserError("用户名已存在")
        if self._store.find_one("im_users", {"email": email}) is not None:
            raise DuplicateUserError("邮箱已存在")

        salt = secrets.token_hex(16)
        record = {
            "user_id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "display_name": display_name.strip() or username,
            "avatar_url": avatar_url,
            "password_salt": salt,
            "password_hash": self._hash_password(password, salt),
        }
        user = self._store.insert_one("im_users", record)
        token = self._create_session(user)
        return {"user": self._public_user(user), "token": token}

    def login(self, *, username: str, password: str) -> dict[str, Any]:
        login_id = username.strip()
        user = (
            self._store.find_one("im_users", {"username": login_id})
            or self._store.find_one("im_users", {"email": login_id.lower()})
        )
        if user is None or not self._verify_password(password, user):
            raise AuthError("用户名或密码错误")
        token = self._create_session(user)
        return {"user": self._public_user(user), "token": token}

    def current_user(self, token: str) -> dict[str, Any]:
        session = self._store.find_one("im_sessions", {"token": token})
        if session is None or session.get("revoked"):
            raise AuthError("登录已失效")
        if float(session.get("expires_at", 0)) < time.time():
            raise AuthError("登录已过期")
        user = self._store.find_one("im_users", {"user_id": session.get("user_id")})
        if user is None:
            raise AuthError("用户不存在")
        return self._public_user(user)

    def logout(self, token: str) -> dict[str, Any]:
        session = self._store.find_one("im_sessions", {"token": token})
        if session is None:
            raise AuthError("登录已失效")
        self._store.update_one("im_sessions", {"token": token}, {"revoked": True})
        return {"logged_out": True}

    def _validate_credentials(self, *, username: str, email: str, password: str) -> None:
        if len(username) < 2:
            raise ValueError("用户名至少 2 个字符")
        if "@" not in email:
            raise ValueError("邮箱格式不正确")
        if len(password) < 6:
            raise ValueError("密码至少 6 个字符")

    def _create_session(self, user: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(32)
        self._store.insert_one(
            "im_sessions",
            {
                "token": token,
                "user_id": user["user_id"],
                "username": user["username"],
                "expires_at": time.time() + self._session_ttl_seconds,
                "revoked": False,
            },
        )
        return token

    def _hash_password(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120_000,
        )
        return digest.hex()

    def _verify_password(self, password: str, user: dict[str, Any]) -> bool:
        expected = str(user.get("password_hash", ""))
        salt = str(user.get("password_salt", ""))
        actual = self._hash_password(password, salt)
        return hmac.compare_digest(actual, expected)

    def _public_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": user.get("user_id", ""),
            "username": user.get("username", ""),
            "email": user.get("email", ""),
            "display_name": user.get("display_name") or user.get("username", ""),
            "avatar_url": user.get("avatar_url", ""),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        }
