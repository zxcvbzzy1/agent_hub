from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from im_backend.application.event_stream import RoomEventStreamService
from im_backend.application.services import AgentCatalogService, IMService
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge
from im_backend.infra.storage.artifacts import ArtifactStorage


class IMContainer:
    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.bridge = AgentFlowBridge()
        self.store = self.bridge.store
        self.room_events = RoomEventStreamService(self.store)
        self.im = IMService(
            store=self.store,
            bridge=self.bridge,
            room_events=self.room_events,
            default_workdir=os.getenv("IM_AGENT_WORKDIR", str(self.repo_root.parent)),
        )
        self.agents = AgentCatalogService(self.bridge)
        self.artifacts = ArtifactStorage(
            self.store,
            os.getenv("IM_ARTIFACT_ROOT", str(self.repo_root / "im_backend" / "storage" / "artifacts")),
        )


@lru_cache(maxsize=1)
def get_container() -> IMContainer:
    return IMContainer()


def get_im_service() -> IMService:
    return get_container().im


def get_agent_catalog() -> AgentCatalogService:
    return get_container().agents


def get_room_events() -> RoomEventStreamService:
    return get_container().room_events


def get_artifact_storage() -> ArtifactStorage:
    return get_container().artifacts
