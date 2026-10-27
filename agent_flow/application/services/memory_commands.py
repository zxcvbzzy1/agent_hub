"""Explicit user memory commands, independent of automatic run archiving."""
from __future__ import annotations

import asyncio
import re

from application.services.long_memory import digest, stable_id
from domain.memory.long.models import MemoryScope, MemorySource, MemoryBlock
from domain.run_context import current_run_id


class MemoryCommandService:
    def __init__(self, memory, store):
        self.memory, self.store = memory, store

    async def execute(self, operation, query="", content="", block_id="", request_quote=""):
        if any(not isinstance(value, str) for value in (operation, query, content, block_id, request_quote)):
            raise ValueError("记忆操作参数必须是字符串")
        record = self.store.find_one("runs", {"run_id": current_run_id.get()}) or {}
        scope = record.get("memory_scope") or {}
        user = scope.get("user_id")
        if not user:
            raise ValueError("记忆操作需要可信的当前用户身份")
        if operation == "search":
            if not query.strip():
                raise ValueError("请提供记忆查询")
            hits = await asyncio.to_thread(self.memory.recall, MemoryScope(**scope), query,
                                          run_id="", record_usage=False)
            return {"items": [{"block_id": b["block_id"], "content": b["content"]} for b in hits]}
        if operation not in {"remember", "correct", "forget"}:
            raise ValueError("不支持的记忆操作")
        question = record.get("user_question") or ""
        if not request_quote.strip() or request_quote not in question:
            raise ValueError("修改记忆必须引用当前用户明确要求修改记忆的原话")
        if not re.search(r"记住|记下|记得|记忆|忘记|更正|纠正|remember|forget|correct|memory", request_quote, re.I):
            raise ValueError("用户未明确要求修改长期记忆；请先确认意图")
        if operation in {"correct", "forget"}:
            if not block_id:
                raise ValueError("请先查询并确定唯一的记忆 ID；不明确时向用户澄清")
            await asyncio.to_thread(self.memory._owned_block, user, block_id, active=True)
        if operation == "forget":
            count = await asyncio.to_thread(self.memory.delete_memory, user, block_id)
            return {"deleted": count}
        if not content.strip() or len(content) > 20000:
            raise ValueError("记忆内容不能为空或超过 20000 字符")
        block = await asyncio.to_thread(self._remember, record, content, operation, block_id)
        if operation == "correct":
            await asyncio.to_thread(self.memory.expire_memory, user, block_id)
            await asyncio.to_thread(self.memory.repository.update_block, block_id,
                                   {"status": "superseded", "superseded_by_block_ids": [block["block_id"]]})
        consolidated = await self.memory.documents.consolidate_user(user) if self.memory.documents else False
        return {"block_id": block["block_id"], "saved": True, "l1_pending": not consolidated,
                "message": "记忆已保存，L1 文件等待后台更新" if not consolidated else "记忆及 L1 文件已更新"}

    def _remember(self, record, content, operation, target):
        scope = MemoryScope(**record["memory_scope"])
        sid = stable_id(f"explicit:{record['run_id']}:{operation}:{target}:{digest(content)}")
        existing = self.memory.repository.blocks({"block_id": sid})
        if existing:
            return existing[0]
        question = record["user_question"].replace("\r\n", "\n").replace("\r", "\n")
        text = "# 用户明确修改记忆\n\n" + question + "\n"
        source = MemorySource(source_id=sid, **scope.to_dict(), source_kind="explicit",
            file_path=self.memory._path(scope, "explicit", sid), content_hash=digest(text),
            run_id=record["run_id"], message_id=record.get("source_message_id", ""),
            run_status=record.get("status", "running"), index_status="ready").to_dict()
        source.update(project_path=record.get("project_path", ""), started_at=record.get("started_at"))
        self.memory.files.write(source["file_path"], text)
        self.memory.repository.put_source(source)
        ref = {k: source[k] for k in ("source_id", "file_path", "run_id", "run_status", "message_id",
                                     "room_id", "conversation_id", "project_path")}
        ref.update(start_line=3, end_line=2 + len(question.split("\n")), section_kind="qa", event={})
        block = MemoryBlock(block_id=sid, memory_id=sid, **scope.to_dict(), source_id=sid,
            file_path=source["file_path"], start_line=ref["start_line"], end_line=ref["end_line"],
            content=content.strip(), content_hash=digest(content.strip()), token_count=self.memory.counter.count(content),
            token_count_method=self.memory.counter.name, section_kind="extracted", memory_type="explicit",
            run_id=record["run_id"], run_status=source["run_status"], message_id=source["message_id"],
            evidence_refs=[ref], evidence_source_ids=[sid], metadata={"explicit_user_command": True}).to_dict()
        return self.memory.repository.put_block(block)
