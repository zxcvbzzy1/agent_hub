"""IM-only storage for memory management and user retrieval preferences."""

SETTINGS = "long_memory_settings"
BLOCKS = "long_memory_blocks"


class MemoryManagementRepository:
    def __init__(self, store, *, ensure_indexes: bool = True):
        self.store = store
        if ensure_indexes:
            store.ensure_index(SETTINGS, [("user_id", 1)], unique=True)
            store.ensure_index(BLOCKS, [("user_id", 1), ("updated_at", -1), ("block_id", 1)])

    def get_settings(self, user_id: str) -> dict | None:
        row = self.store.find_one(SETTINGS, {"user_id": user_id})
        return row["config"] if row else None

    def save_settings(self, user_id: str, config: dict) -> None:
        self.store.update_one(SETTINGS, {"user_id": user_id}, {"config": config}, upsert=True)

    def page_blocks(self, query: dict, *, page: int, page_size: int) -> tuple[list[dict], int]:
        total = self.store.count(BLOCKS, query)
        rows = self.store.find_many(BLOCKS, query, sort=[("updated_at", -1), ("block_id", 1)],
            skip=(page - 1) * page_size, limit=page_size, projection={"_usage_run_ids": False})
        return rows, total
