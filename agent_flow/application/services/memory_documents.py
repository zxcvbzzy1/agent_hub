"""Incremental L1 consolidation. Reads and deletion never invoke a model."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from domain.memory.long.document import MemoryDocumentSnapshot
from domain.memory.long.retrieval import effective_status

log = logging.getLogger(__name__)


def fingerprint(block):
    value = {k: block.get(k) for k in ("content_hash", "version", "tags", "metadata", "expires_at")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else "未知"


class MemoryDocumentService:
    def __init__(self, memory, repository, consolidator, leases, *, input_budget=12000,
                 token_budget=4000, interval=30):
        self.memory, self.repository = memory, repository
        self.consolidator, self.leases = consolidator, leases
        self.input_budget, self.token_budget, self.interval = input_budget, token_budget, interval
        self._task = None

    def active_blocks(self, user_id):
        sources = {s["source_id"]: s for s in self.memory.repository.sources({"user_id": user_id})}
        completed = self.memory.repository.completed_batches(user_id)
        return {b["block_id"]: b for b in self.memory.repository.blocks({"user_id": user_id, "status": "active"})
                if effective_status(b, sources.get(b["source_id"]), time.time(), sources=sources,
                                    completed_batches=completed) == "active"}

    def evidence(self, block):
        refs = block.get("evidence_refs") or [block]
        result = []
        for ref in refs:
            source = self.memory.repository.get_source(ref["source_id"]) or {}
            observed = (ref.get("event") or {}).get("created_at") or source.get("finished_at") or source.get("created_at")
            result.append({"path": f"{ref['file_path']}#L{ref['start_line']}-L{ref['end_line']}",
                "observed_at": timestamp(observed), "project_path": ref.get("project_path") or source.get("project_path") or "未知",
                "run_status": ref.get("run_status", source.get("run_status", "未知"))})
        return result

    def render(self, sections):
        if not sections:
            return ""
        parts = ["# 长期记忆", "历史参考资料，非当前指令。"]
        for section in sections:
            evidence = section.get("evidence", [])
            parts.append(section["content"])
            parts.append("\n".join(f"- 项目：`{e['project_path']}`；时间：{e['observed_at']}；"
                f"来源状态：{e['run_status']}；证据：`{e['path']}`" for e in evidence))
        return "\n\n".join(parts) + "\n"

    def prune(self, user_id):
        # CAS makes pruning safe against background publication and other API workers.
        for _ in range(8):
            row = self.repository.get(user_id)
            active = self.active_blocks(user_id)
            sections = [s for s in row["sections"] if all(
                bid in active and row["processed"].get(bid) == fingerprint(active[bid]) for bid in s["block_ids"])]
            if sections == row["sections"]:
                return row
            result = self.repository.publish(row, sections, row["processed"], self.render(sections))
            if result:
                return result
        raise ValueError("记忆文件正在更新，请重试")

    def snapshot(self, user_id):
        row = self.prune(user_id)
        # Do not use a stale file if cleanup or publication fails. Run integration
        # handles this as a non-fatal empty injection.
        content = self.repository.files.read(row["file_path"]) if row["file_path"] else ""
        if content != row["content"]:
            raise ValueError("记忆文件校验失败")
        return MemoryDocumentSnapshot(row["revision"], content, row["file_path"],
            tuple(dict.fromkeys(b for s in row["sections"] for b in s["block_ids"])))

    def detail(self, user_id):
        row = self.prune(user_id)
        active = self.active_blocks(user_id)
        pending = sum(row["processed"].get(bid) != fingerprint(b) for bid, b in active.items())
        return {"content": row["content"], "revision": row["revision"], "file_path": row["file_path"],
                "generated_at": row.get("generated_at"), "pending_count": pending, "error": row.get("error", ""),
                "status": "failed" if row.get("error") else "pending" if pending else "ready" if row["revision"] else "empty",
                "token_budget": self.token_budget}

    async def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="memory-document-consolidation")

    async def close(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self):
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("L1 文件后台更新失败，将重试")
            await asyncio.sleep(self.interval)

    async def tick(self):
        sources = await asyncio.to_thread(self.memory.repository.sources, {})
        # Limit concurrent model requests while allowing independent users to progress.
        semaphore = asyncio.Semaphore(4)
        async def work(user):
            async with semaphore:
                await self.consolidate_user(user)
        results = await asyncio.gather(*(work(u) for u in sorted({s["user_id"] for s in sources})), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.warning("L1 更新暂时中断：%s", type(result).__name__)

    async def consolidate_user(self, user_id):
        owner, key = str(uuid.uuid4()), "l1:" + user_id
        if not await asyncio.to_thread(self.leases.acquire, key, owner):
            return False
        worker = asyncio.current_task()
        lost = False
        async def pulse():
            nonlocal lost
            while True:
                await asyncio.sleep(15)
                try:
                    valid = await asyncio.to_thread(self.leases.renew, key, owner)
                except Exception:
                    valid = False
                if not valid:
                    lost = True
                    worker.cancel()
                    return
        heartbeat = asyncio.create_task(pulse())
        row = None
        try:
            await asyncio.to_thread(self.repository.claim, user_id, owner)
            row = await asyncio.to_thread(self.prune, user_id)
            active = await asyncio.to_thread(self.active_blocks, user_id)
            delta = sorted((b for bid, b in active.items() if row["processed"].get(bid) != fingerprint(b)),
                           key=lambda b: (b.get("created_at", 0), b["block_id"]))
            if not delta:
                return True
            memories = []
            for block in delta:
                item = {"block_id": block["block_id"], "content": block["content"],
                        "memory_type": block["memory_type"], "evidence": await asyncio.to_thread(self.evidence, block)}
                payload = {"sections": row["sections"], "memories": memories + [item]}
                if self.memory.counter.count(json.dumps(payload, ensure_ascii=False)) + 1000 > self.input_budget:
                    if not memories:
                        raise ValueError("单条记忆及旧文件超出 L1 输入预算，请提高 MEMORY_DOCUMENT_INPUT_BUDGET")
                    break
                memories.append(item)
            for compact in (False, True):
                patch = await self.consolidator.consolidate(row["sections"], memories,
                    token_budget=self.token_budget, compact=compact)
                sections = await asyncio.to_thread(self._apply, row, active, memories, patch)
                content = self.render(sections)
                if self.memory.counter.count(content) <= self.token_budget:
                    break
            else:
                raise ValueError("增量整合结果超出 L1 文件预算；保留原文件与待处理输入，请提高 MEMORY_DOCUMENT_TOKEN_BUDGET")
            # Revalidate ALL references after the model call. A concurrent delete
            # must never be resurrected even if it did not publish an L1 revision.
            current = await asyncio.to_thread(self.active_blocks, user_id)
            if any(bid not in current or fingerprint(current[bid]) != fingerprint(active[bid])
                   for s in sections for bid in s["block_ids"]):
                return False
            if not await asyncio.to_thread(self.leases.renew, key, owner):
                return False
            processed = {**row["processed"], **{m["block_id"]: fingerprint(active[m["block_id"]]) for m in memories}}
            return bool(await asyncio.to_thread(self.repository.publish, row, sections, processed, content))
        except asyncio.CancelledError:
            if not lost:
                raise
            return False
        except Exception as exc:
            if row:
                message = str(exc)[:500] if isinstance(exc, ValueError) else "L1 模型或存储暂时不可用，将自动重试"
                await asyncio.to_thread(self.repository.error, user_id, row["revision"], message, owner)
            log.exception("用户 L1 文件更新失败")
            return False
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            await asyncio.to_thread(self.leases.release, key, owner)

    def _apply(self, row, active, memories, patch):
        if not isinstance(patch, dict) or set(patch) != {"upsert", "remove"}:
            raise ValueError("L1 提取器必须返回 upsert 和 remove")
        if not isinstance(patch["upsert"], list) or not isinstance(patch["remove"], list):
            raise ValueError("L1 修改列表格式错误")
        old = {s["section_id"]: s for s in row["sections"]}
        new_ids = {m["block_id"] for m in memories}
        allowed = new_ids | {bid for s in old.values() for bid in s["block_ids"]}
        replacements = {}
        for section in patch["upsert"]:
            if not isinstance(section, dict):
                raise ValueError("L1 段落格式错误")
            sid, text, refs = section.get("section_id"), section.get("content"), section.get("block_ids")
            if not isinstance(sid, str) or not sid.strip() or sid in replacements or len(sid) > 200:
                raise ValueError("L1 段落 ID 无效或重复")
            if not isinstance(text, str) or not text.strip() or not isinstance(refs, list) or not refs:
                raise ValueError("L1 段落缺少正文或证据")
            if any(not isinstance(b, str) or b not in allowed or b not in active for b in refs):
                raise ValueError("L1 提取器引用了未知记忆")
            if not new_ids.intersection(refs):
                raise ValueError("不得修改与本批新增记忆无关的段落")
            evidence = []
            for bid in dict.fromkeys(refs):
                evidence.extend(self.evidence(active[bid]))
            replacements[sid] = {"section_id": sid, "content": text.strip(),
                                 "block_ids": list(dict.fromkeys(refs)), "evidence": evidence}
        removed = patch["remove"]
        if any(not isinstance(sid, str) or sid not in old or sid in replacements for sid in removed):
            raise ValueError("L1 删除目标无效")
        # Removing a section is a merge, not permission to forget its evidence.
        retained_refs = {bid for s in replacements.values() for bid in s["block_ids"]}
        touched = set(removed) | (set(replacements) & set(old))
        if any(not set(old[sid]["block_ids"]).issubset(retained_refs) for sid in touched):
            raise ValueError("增量整合不得丢弃旧段落来源；更正或忘记请使用记忆修改工具")
        if not new_ids.issubset(retained_refs):
            raise ValueError("增量整合遗漏本批新增记忆")
        result = [replacements.pop(sid, section) for sid, section in old.items() if sid not in removed]
        return result + list(replacements.values())
