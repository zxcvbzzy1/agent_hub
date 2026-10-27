"""Versioned L1 files with a compare-and-swap MongoDB publication pointer."""
from __future__ import annotations

from pymongo.errors import DuplicateKeyError

COLLECTION = "long_memory_documents"


class MongoMemoryDocuments:
    def __init__(self, store, files):
        self.store, self.files = store, files
        store.ensure_index(COLLECTION, [("user_id", 1)], unique=True)

    def get(self, user_id):
        row = self.store.find_one(COLLECTION, {"user_id": user_id})
        if row:
            return row
        try:
            self.store.update_operators(COLLECTION, {"user_id": user_id}, {"$setOnInsert": {
                "user_id": user_id, "revision": 0, "sections": [], "processed": {},
                "content": "", "file_path": "", "error": "", "generated_at": None,
                "writer_token": "",
            }}, upsert=True)
        except DuplicateKeyError:
            pass
        return self.store.find_one(COLLECTION, {"user_id": user_id})

    def claim(self, user_id, owner):
        self.get(user_id)
        return self.store.update_one(COLLECTION, {"user_id": user_id}, {"writer_token": owner})

    def publish(self, previous, sections, processed, content):
        import time
        import uuid
        from urllib.parse import quote
        revision = previous["revision"] + 1
        user = quote(previous["user_id"], safe="").replace(".", "%2E")
        # Unique immutable paths also make ambiguous writes safe to retry. L3's
        # insert-only file adapter is deliberately not changed to allow overwrite.
        path = f"{user}/l1/{revision}-{uuid.uuid4().hex}/MEMORY.md"
        self.files.write(path, content)
        return self.store.update_one(COLLECTION,
            {"user_id": previous["user_id"], "revision": previous["revision"],
             "writer_token": previous.get("writer_token", "")}, {
                "revision": revision, "sections": sections, "processed": processed,
                "content": content, "file_path": path, "error": "", "generated_at": time.time(),
            })

    def error(self, user_id, revision, message, owner):
        self.store.update_one(COLLECTION, {"user_id": user_id, "revision": revision, "writer_token": owner}, {"error": message})
