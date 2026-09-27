"""Authenticated memory queries and settings; mutations of memory are not exposed."""
import re
import time
from im_backend.domain.memory_settings import RetrievalSettings
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from domain.memory.long import MemoryScope, RecallOptions
from domain.memory.long.retrieval import effective_status
from domain.memory.long.processing import ProcessingConfig


class MemoryManagementService:
    def __init__(self, memory, store, management_repository):
        self.memory, self.store = memory, store
        self.repository = memory.repository
        self.management_repository = management_repository

    def _source(self, user_id, source_id):
        source = self.repository.get_source(source_id)
        if not source or source["user_id"] != user_id:
            raise KeyError("记忆来源不存在")
        return source

    def _labels(self, item):
        room_id, conversation_id = item.get("room_id", ""), item.get("conversation_id", "")
        room = self.store.find_one("im_rooms", {"room_id": room_id}) or {}
        conversation = self.store.find_one("im_conversations", {"conversation_id": conversation_id}) or {}
        return {"room_name": room.get("title") or {"direct": "私聊", "standalone": "独立运行"}.get(room_id, room_id),
                "conversation_name": conversation.get("title") or conversation_id}

    def _summary(self, block, source, now, *, sources=None, completed=None):
        fields = ("block_id", "memory_id", "version", "source_id", "room_id", "conversation_id", "section_kind",
                  "memory_type", "tags", "token_count", "token_count_method", "usage_count", "updated_at",
                  "file_path", "start_line", "end_line", "run_status", "expires_at", "batch_id", "evidence_refs")
        return {**{key: block.get(key) for key in fields}, "summary": block["content"][:240],
                "status": effective_status(block, source, now, sources=sources, completed_batches=completed), **self._labels(block)}

    def list_blocks(self, user_id, *, q="", status="active", room_id=None, conversation_id=None,
                    page=1, page_size=20):
        now = time.time()
        sources = {s["source_id"]: s for s in self.repository.sources({"user_id": user_id})}
        deleted = [sid for sid, s in sources.items() if s.get("deleted_at") is not None]
        ready = [sid for sid, s in sources.items() if s.get("deleted_at") is None and s["index_status"] == "ready"]
        unavailable = [sid for sid in sources if sid not in ready]
        completed = self.repository.completed_batches(user_id)
        not_deleted = {"source_id": {"$nin": deleted}, "evidence_source_ids": {"$nin": deleted}}
        is_deleted = {"$or": [{"status": "deleted"}, {"source_id": {"$in": deleted}},
                              {"evidence_source_ids": {"$in": deleted}}]}
        published = {"$or": [{"batch_id": None}, {"batch_id": {"$in": list(completed)}}]}
        unexpired = {"$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]}
        clauses = [{"user_id": user_id}]
        if q.strip():
            pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
            clauses.append({"$or": [{"content": pattern}, {"tags": pattern}]})
        for key, value in (("room_id", room_id), ("conversation_id", conversation_id)):
            if value:
                matching_sources = [sid for sid, source in sources.items() if source.get(key) == value]
                clauses.append({"$or": [{key: value}, {"evidence_source_ids": {"$in": matching_sources}}]})
        if status == "deleted":
            clauses.append(is_deleted)
        elif status != "all":
            clauses.append(not_deleted)
            if status == "active":
                clauses.extend([{"status": "active", "source_id": {"$in": ready},
                                 "evidence_source_ids": {"$nin": unavailable}}, unexpired, published])
            elif status == "expired":
                clauses.append({"$or": [{"status": "expired"}, {"status": "active",
                    "expires_at": {"$ne": None, "$lte": now}}]})
            elif status == "unavailable":
                clauses.extend([{"status": "active"}, unexpired, {"$or": [
                    {"source_id": {"$nin": ready + deleted}}, {"evidence_source_ids": {"$in": unavailable}},
                    {"batch_id": {"$ne": None, "$nin": list(completed)}}]}])
            else:
                clauses.append({"status": status})
        rows, total = self.management_repository.page_blocks({"$and": clauses}, page=page, page_size=page_size)
        return {"items": [self._summary(b, sources.get(b["source_id"]), now, sources=sources, completed=completed) for b in rows],
                "total": total, "page": page, "page_size": page_size}

    def block_detail(self, user_id, block_id):
        rows = self.repository.blocks({"user_id": user_id, "block_id": block_id})
        if not rows:
            raise KeyError("记忆不存在")
        block = rows[0]
        source = self._source(user_id, block["source_id"])
        now = time.time()
        related_ids = block.get("derived_from_block_ids", []) + block.get("superseded_by_block_ids", [])
        related = self.repository.blocks({"user_id": user_id, "$or": [
            {"memory_id": block["memory_id"]}, {"block_id": {"$in": related_ids}}]})
        related_sources = {s["source_id"]: s for s in self.repository.sources({"user_id": user_id})}
        completed = self.repository.completed_batches(user_id)
        evidence = []
        for ref in block.get("evidence_refs", []):
            # Check every reference, including references beyond the compatibility anchor.
            self._source(user_id, ref["source_id"])
            evidence.append({**ref, **self._labels(ref)})
        return {"item": {**block, **self._summary(block, source, now, sources=related_sources, completed=completed),
                         "evidence_refs": evidence}, "source": source,
                "related": [self._summary(b, related_sources.get(b["source_id"]), now,
                    sources=related_sources, completed=completed) for b in related
                            if b["block_id"] != block_id and b["source_id"] in related_sources]}

    def source_detail(self, user_id, source_id):
        source = self._source(user_id, source_id)
        return {"item": {**source, **self._labels(source), "content": self.memory.files.read(source["file_path"])}}

    def scopes(self, user_id):
        rooms, conversations = {}, {}
        for source in self.repository.sources({"user_id": user_id}):
            labels = self._labels(source)
            room_id, conversation_id = source["room_id"], source["conversation_id"]
            rooms[room_id] = {"value": room_id, "label": labels["room_name"]}
            conversations[(room_id, conversation_id)] = {
                "value": conversation_id, "label": labels["conversation_name"], "room_id": room_id}
        return {"rooms": list(rooms.values()), "conversations": list(conversations.values())}

    def settings(self, user_id):
        stored = self.management_repository.get_settings(user_id)
        return {"item": RetrievalSettings(**(stored or {})).to_dict(),
                "defaults": RetrievalSettings().to_dict()}

    def save_settings(self, user_id, config: RetrievalSettings):
        if not user_id:
            raise ValueError("缺少用户身份")
        self.management_repository.save_settings(user_id, config.to_dict())
        return {"item": config.to_dict()}

    def recall_test(self, user_id, query, config=None):
        if not query.strip():
            raise ValueError("请输入用于召回的问题")
        options = RecallOptions(**config.to_dict()) if config else None
        result = self.memory.recall_result(MemoryScope(user_id), query.strip(), config=options).to_dict()
        for block in result["selected"]:
            block.update(self._labels(block))
        return {"item": result}

    def _processing(self):
        if not self.memory.processing:
            raise ValueError("当前服务未启用记忆生成")
        return self.memory.processing

    def processing_settings(self, user_id):
        processor = self._processing()
        snapshot = processor.repository.settings(user_id)
        return {"item": snapshot["config"], "revision": snapshot["revision"],
                "defaults": ProcessingConfig().to_dict(), "max_wait_hours": 24,
                "server": processor.readiness()}

    def save_processing_settings(self, user_id, config):
        self._processing().repository.save_settings(user_id, config)
        return self.processing_settings(user_id)

    def batches(self, user_id, page=1, page_size=20):
        return self._processing().repository.page_batches(user_id, page, page_size)

    def batch_detail(self, user_id, batch_id):
        repository = self._processing().repository
        rows = repository.batches({"user_id": user_id, "batch_id": batch_id})
        if not rows:
            raise KeyError(batch_id)
        batch = {k: v for k, v in rows[0].items() if k not in {"steps", "owner"}}
        candidates = repository.candidates(batch_id)
        batch["candidate_count"] = len(candidates)
        batch["classified_count"] = sum(c["status"] in {"accepted", "rejected"} for c in candidates)
        batch["accepted_count"] = sum(c["status"] == "accepted" for c in candidates)
        # Keep responses bounded. All per-candidate records remain in MongoDB.
        batch["candidates"] = [{k: v for k, v in c.items() if k != "content"} | {"summary": c["content"][:240]}
                               for c in candidates[:100]]
        batch["candidates_truncated"] = len(candidates) > 100
        batch["sources"] = [{k: source[k] for k in ("source_id", "run_id", "room_id", "conversation_id", "run_status")}
                            for source in (self._source(user_id, sid) for sid in batch["source_ids"])]
        return {"item": batch}

    def retry_batch(self, user_id, batch_id):
        self._processing().repository.retry(user_id, batch_id)
        return self.batch_detail(user_id, batch_id)
