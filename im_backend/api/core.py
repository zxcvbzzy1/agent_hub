from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from im_backend.infra.env import load_backend_env

load_backend_env()

from im_backend.application.auth_service import AuthError, AuthService
from im_backend.application.event_stream import RoomEventStreamService
from im_backend.application.agent_service import IMAgentService
from im_backend.application.services import IMService
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge
from im_backend.infra.storage.artifacts import ArtifactStorage


class IMContainer:
    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.bridge = AgentFlowBridge()
        self.store = self.bridge.store
        self.room_events = RoomEventStreamService(self.store)
        self.auth = AuthService(self.store)
        self.im = IMService(
            store=self.store,
            bridge=self.bridge,
            room_events=self.room_events,
            default_workdir=os.getenv("IM_AGENT_WORKDIR", str(self.repo_root.parent)),
        )
        self.agents = self.im.agents
        self.artifacts = ArtifactStorage(
            self.store,
            os.getenv("IM_ARTIFACT_ROOT", str(self.repo_root / "im_backend" / "storage" / "artifacts")),
        )


@lru_cache(maxsize=1)
def get_container() -> IMContainer:
    return IMContainer()


def get_im_service() -> IMService:
    return get_container().im


def get_auth_service() -> AuthService:
    return get_container().auth


def get_agent_catalog() -> IMAgentService:
    return get_container().agents


def get_room_events() -> RoomEventStreamService:
    return get_container().room_events


def get_artifact_storage() -> ArtifactStorage:
    return get_container().artifacts


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录")
    try:
        return auth.current_user(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录")
    return credentials.credentials
