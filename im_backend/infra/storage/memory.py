"""IM-only storage for memory management and user retrieval preferences."""

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()
from infra.memory.settings import MongoMemorySettings

BLOCKS = "long_memory_blocks"


class MemoryManagementRepository:
    def __init__(self, store, *, ensure_indexes: bool = True):
        self.store = store
        self.settings = MongoMemorySettings(store, ensure_indexes=ensure_indexes)
        if ensure_indexes:
            store.ensure_index(BLOCKS, [("user_id", 1), ("updated_at", -1), ("block_id", 1)])

    def get_settings(self, user_id: str) -> dict | None:
        return self.settings.retrieval(user_id)

    def save_settings(self, user_id: str, config: dict) -> None:
        self.settings.save_retrieval(user_id, config)

    def page_blocks(self, query: dict, *, page: int, page_size: int) -> tuple[list[dict], int]:
        total = self.store.count(BLOCKS, query)
        rows = self.store.find_many(BLOCKS, query, sort=[("updated_at", -1), ("block_id", 1)],
            skip=(page - 1) * page_size, limit=page_size, projection={"_usage_run_ids": False})
        return rows, total
