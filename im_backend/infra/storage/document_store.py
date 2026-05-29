from __future__ import annotations

import os

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
from im_backend.infra.env import load_backend_env

load_backend_env()
ensure_agent_flow_path()

from infra.db.mongodb import DocumentStore  # type: ignore  # noqa: E402


def create_document_store() -> DocumentStore:
    """Create im_backend's own store, independent from agent_flow API DB."""
    return DocumentStore(
        os.getenv("IM_MONGO_URL", "mongodb://localhost:27017/"),
        os.getenv("IM_MONGO_DB", "im_backend"),
    )


def get_document_store() -> DocumentStore:
    return create_document_store()
