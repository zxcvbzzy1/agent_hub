from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from im_backend.infra.env import load_backend_env

load_backend_env()

from im_backend.application.auth_service import AuthError, AuthService
from im_backend.application.services.messaging.agent_builder import AgentBuilderService
from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.facade import IMService
from im_backend.application.services.platform.bootstrap import StaticConfigImportService
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge
from im_backend.infra.storage.artifacts import ArtifactStorage
from im_backend.infra.storage.document_store import create_document_store


class IMContainer:
    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.store = create_document_store()
        self._ensure_message_indexes()
        self._ensure_event_indexes()
        self.bridge = AgentFlowBridge(store=self.store, repo_root=self.repo_root)
        self.static_imports = StaticConfigImportService(bridge=self.bridge)
        self.static_import_result = self.static_imports.import_defaults()
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

    def _ensure_message_indexes(self) -> None:
        """支撑聊天记录懒加载窗口查询的索引（幂等；内存兜底为 no-op）。"""
        # 单聊：按 conversation_id 等值 + created_at 排序/范围取窗口。
        self.store.ensure_index("im_messages", [("conversation_id", 1), ("created_at", 1)])
        # 群聊：按 room_id(+conversation_id) 等值 + created_at 取窗口。
        self.store.ensure_index("im_messages", [("room_id", 1), ("conversation_id", 1), ("created_at", 1)])
        # 游标 / 各处 message_id 精确查改用。
        self.store.ensure_index("im_messages", [("message_id", 1)])

    def _ensure_event_indexes(self) -> None:
        """事件流读取/回放的核心索引（幂等；内存兜底为 no-op）。

        事件是高写入集合，只建命中热读的核心索引以控制写放大：
        - im_events：按 scope_id 等值 + created_at 排序回放房间/会话事件流；同时覆盖按 scope_id 的批量清理。
        - events（runtime）：按 run_id 等值 + created_at 排序——每次进会话 SSE 回放、每次展开 trace
          详情(GET /runs/{run_id}/events)都走这条；同时覆盖按 run_id 的批量清理。
        created_at 升序索引即可同时服务升/降序排序，Mongo 可反向遍历。
        """
        self.store.ensure_index("im_events", [("scope_id", 1), ("created_at", 1)])
        self.store.ensure_index("events", [("run_id", 1), ("created_at", 1)])


@lru_cache(maxsize=1)
def get_container() -> IMContainer:
    return IMContainer()


def get_im_service() -> IMService:
    return get_container().im


def get_auth_service() -> AuthService:
    return get_container().auth


def get_agent_catalog() -> IMAgentService:
    return get_container().agents


def get_agent_builder() -> AgentBuilderService:
    # 每次请求新建（构造很轻），让 system prompt 始终反映最新的工具目录（工具可运行时上传）。
    return AgentBuilderService(agents=get_container().agents)


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
