"""L1 integration using real file/storage adapters and fake model/Redis only."""
import asyncio
import copy
import json
import time
from types import SimpleNamespace

import mongomock
import pytest
from fakeredis import FakeRedis
from pymongo import ReturnDocument

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from application.services.long_memory import LongTermMemoryService
from application.services.memory_commands import MemoryCommandService
from application.services.memory_documents import MemoryDocumentService
from application.services.memory_runtime import RunMemoryCoordinator
from domain.context.context import ContextEngine
from domain.memory.long.models import MemoryScope
from domain.memory.long.providers import MemoryDocumentProvider
from domain.run_context import current_run_id
from infra.db.mongodb import DocumentStore
from infra.memory.documents import MongoMemoryDocuments
from infra.memory.files import MarkdownSourceFiles
from infra.memory.mongodb import MongoMemoryRepository
from infra.memory.processing import MemoryProcessingRepository


class Consolidator:
    def __init__(self):
        self.calls = []
        self.callback = None
        self.fail = False

    async def consolidate(self, sections, memories, *, token_budget=4000, compact=False):
        self.calls.append(copy.deepcopy((sections, memories)))
        if self.callback:
            await self.callback()
        if self.fail:
            raise ValueError("fake model failed")
        return {"upsert": [{"section_id": m["block_id"], "content": m["content"],
                            "block_ids": [m["block_id"]]} for m in memories], "remove": []}


class MockDocumentStore(DocumentStore):
    def update_one(self, collection, query, updates, upsert=False):
        # mongomock 4.3 re-runs the old CAS query after a projected update,
        # unlike MongoDB. Omit projection and strip _id from the returned copy.
        result = self._db[collection].find_one_and_update(query,
            {"$set": self._stamp(copy.deepcopy(updates), create=False)},
            upsert=upsert, return_document=ReturnDocument.AFTER)
        if result is not None:
            result.pop("_id", None)
        return result


@pytest.fixture
def document_memory(tmp_path):
    store = MockDocumentStore.__new__(MockDocumentStore)
    store._db = mongomock.MongoClient().db
    memory = LongTermMemoryService(MongoMemoryRepository(store), MarkdownSourceFiles(tmp_path))
    leases = MemoryProcessingRepository(store, redis_client=FakeRedis(decode_responses=True))
    memory.documents = MemoryDocumentService(memory, MongoMemoryDocuments(store, memory.files), Consolidator(), leases)
    return memory


def archive(memory, run_id="one", user="alice", project="/project/one", question="用户偏好 Python"):
    return memory.archive_run({"run_id": run_id, "memory_scope": MemoryScope(user, "room", "chat").to_dict(),
        "status": "finished", "started_at": 1700000000, "finished_at": 1700000060,
        "project_path": project, "user_question": question, "final": "已完成"}, [])


@pytest.mark.asyncio
async def test_incremental_restart_evidence_and_user_isolation(document_memory):
    memory = document_memory
    archive(memory)
    assert memory.documents.snapshot("alice").content == ""
    assert await memory.documents.consolidate_user("alice")
    first = memory.documents.snapshot("alice")
    assert "/project/one" in first.content and "2023-11-14" in first.content
    assert "#L" in first.content and "finished" in first.content
    assert memory.files.read(first.file_path) == first.content
    original = copy.deepcopy(memory.documents.repository.get("alice")["sections"])
    archive(memory, "two", project="/project/two", question="第二个项目用 Vue")
    # New L2 does not block the next run from reading the existing file.
    assert memory.documents.snapshot("alice") == first
    assert await memory.documents.consolidate_user("alice")
    row = memory.documents.repository.get("alice")
    assert row["sections"][0] == original[0]
    assert len(memory.documents.consolidator.calls[-1][1]) == 1
    assert "/project/two" in row["content"]
    restarted = MemoryDocumentService(memory, memory.documents.repository, Consolidator(), memory.documents.leases)
    assert await restarted.consolidate_user("alice")
    assert restarted.consolidator.calls == []
    assert restarted.snapshot("bob").content == ""


@pytest.mark.asyncio
async def test_llm_adapter_publishes_incremental_document_through_mock_http(document_memory, monkeypatch):
    import httpx
    import openai
    from infra.memory.extraction import LLMExtractionAdapter

    requests = []
    def handle(request):
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        inputs = json.loads(payload["messages"][1]["content"])
        requests.append(inputs)
        patch = {"upsert": [{"section_id": m["block_id"], "content": m["content"],
                             "block_ids": [m["block_id"]]} for m in inputs["memories"]], "remove": []}
        return httpx.Response(200, json={"id": "completion", "object": "chat.completion", "created": 1,
            "model": "consolidator-version", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(patch)}}]})

    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "test-consolidator")
    monkeypatch.setenv("MEMORY_EXTRACTION_BASE_URL", "https://memory.invalid/v1")
    monkeypatch.setenv("MEMORY_EXTRACTION_API_KEY", "fake-test-key")
    original = openai.AsyncOpenAI
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: original(**kwargs,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle))))
    llm = SimpleNamespace(model="existing", url="https://existing.invalid", max_tokens=2048)
    memory = document_memory
    memory.documents.consolidator = LLMExtractionAdapter(llm)

    archive(memory)
    assert await memory.documents.consolidate_user("alice")
    first = copy.deepcopy(memory.documents.repository.get("alice")["sections"])
    assert "用户偏好 Python" in memory.documents.snapshot("alice").content
    archive(memory, "two", question="第二个项目用 Vue")
    assert await memory.documents.consolidate_user("alice")
    assert memory.documents.repository.get("alice")["sections"][0] == first[0]
    assert "第二个项目用 Vue" in memory.documents.snapshot("alice").content
    assert len(requests) == 2
    assert requests[0]["sections"] == [] and requests[1]["sections"] == first
    assert all(len(request["memories"]) == 1 for request in requests)


@pytest.mark.asyncio
async def test_delete_prunes_without_model_and_keeps_snapshot(document_memory):
    memory = document_memory
    archive(memory)
    archive(memory, "two")
    await memory.documents.consolidate_user("alice")
    snapshot = memory.documents.snapshot("alice")
    row = memory.documents.repository.get("alice")
    kept = row["sections"][1]
    count = len(memory.documents.consolidator.calls)
    memory.delete_memory("alice", row["sections"][0]["block_ids"][0])
    assert memory.documents.repository.get("alice")["sections"] == [kept]
    assert len(memory.documents.consolidator.calls) == count
    assert memory.files.read(snapshot.file_path) == snapshot.content
    await memory.documents.consolidate_user("alice")
    assert len(memory.documents.consolidator.calls) == count


@pytest.mark.asyncio
async def test_concurrent_delete_cannot_publish_or_resurrect(document_memory):
    memory = document_memory
    archive(memory)
    block = next(iter(memory.documents.active_blocks("alice")))
    async def delete():
        memory.delete_memory("alice", block)
    memory.documents.consolidator.callback = delete
    assert not await memory.documents.consolidate_user("alice")
    assert memory.documents.snapshot("alice").content == ""


@pytest.mark.asyncio
async def test_failure_budget_and_invalid_references_keep_pending(document_memory):
    memory = document_memory
    archive(memory)
    await memory.documents.consolidate_user("alice")
    original = memory.documents.snapshot("alice")
    archive(memory, "two")
    memory.documents.consolidator.fail = True
    assert not await memory.documents.consolidate_user("alice")
    assert memory.documents.snapshot("alice") == original
    assert memory.documents.detail("alice")["pending_count"] == 1
    memory.documents.consolidator.fail = False
    memory.documents.token_budget = 1
    assert not await memory.documents.consolidate_user("alice")
    assert memory.documents.snapshot("alice") == original
    memory.documents.token_budget = 4000
    assert await memory.documents.consolidate_user("alice")
    assert memory.documents.detail("alice")["pending_count"] == 0
    with pytest.raises(ValueError, match="未知记忆"):
        memory.documents._apply({"sections": []}, {}, [{"block_id": "real"}],
            {"upsert": [{"section_id": "fake", "content": "invented", "block_ids": ["fake"]}], "remove": []})


@pytest.mark.asyncio
async def test_expiry_and_cleanup_fail_closed(document_memory, monkeypatch):
    memory = document_memory
    source = archive(memory)
    await memory.documents.consolidate_user("alice")
    block = next(iter(memory.documents.active_blocks("alice")))
    memory.repository.update_block(block, {"expires_at": time.time() - 1})
    assert memory.documents.snapshot("alice").content == ""
    archive(memory, "new")
    await memory.documents.consolidate_user("alice")
    def fail(*args):
        raise OSError("disk offline")
    monkeypatch.setattr(memory.documents.repository, "publish", fail)
    memory.delete_sources(run_id="new")
    with pytest.raises(OSError):
        memory.documents.snapshot("alice")


@pytest.mark.asyncio
async def test_static_injection_never_recalls_and_counts_once(document_memory, monkeypatch):
    memory = document_memory
    archive(memory)
    await memory.documents.consolidate_user("alice")
    def fail(*args, **kwargs):
        raise AssertionError("runtime must not dynamically recall L2")
    monkeypatch.setattr(memory, "recall", fail)
    store = memory.repository.store
    record = {"run_id": "live", "memory_scope": MemoryScope("alice").to_dict()}
    store.insert_one("runs", record)
    coordinator = RunMemoryCoordinator(memory, store, None)
    snapshot = await coordinator.prepare(record)
    provider = MemoryDocumentProvider()
    agent = SimpleNamespace(context_engine=ContextEngine([provider], None))
    await coordinator.inject(agent, snapshot, "live")
    await coordinator.inject(agent, snapshot, "live")
    assert provider.content == snapshot.content
    assert snapshot.content in agent.context_engine.build({})
    assert all(b["usage_count"] == 1 for b in memory.repository.blocks({}))
    memory.delete_memory("alice", snapshot.block_ids[0])
    assert provider.content == snapshot.content


@pytest.mark.asyncio
async def test_writer_fencing_and_cas_preserve_newer_document(document_memory):
    docs = document_memory.documents
    old = docs.repository.claim("alice", "old-worker")
    docs.repository.claim("alice", "new-worker")
    assert docs.repository.publish(old, [], {}, "stale") is None
    assert docs.repository.get("alice")["content"] == ""
    # The model must not run while another process holds this user's lease.
    assert docs.leases.acquire("l1:alice", "other-worker")
    try:
        assert not await docs.consolidate_user("alice")
        assert docs.consolidator.calls == []
    finally:
        docs.leases.release("l1:alice", "other-worker")


@pytest.mark.asyncio
async def test_explicit_commands_without_archiving_and_ownership(document_memory):
    memory = document_memory
    record = {"run_id": "command", "status": "running", "memory_scope": MemoryScope("alice", "direct", "dm").to_dict(),
        "project_path": "/project", "source_message_id": "m", "user_question": "请记住我偏好 Python", "run_options": {"memory_write_enabled": False}}
    memory.repository.store.insert_one("runs", record)
    commands = MemoryCommandService(memory, memory.repository.store)
    token = current_run_id.set("command")
    try:
        result = await commands.execute("remember", content="用户偏好 Python", request_quote=record["user_question"])
        assert result["saved"] and not result["l1_pending"]
        assert "用户偏好 Python" in memory.documents.snapshot("alice").content
        assert (await commands.execute("search", query="Python"))["items"][0]["block_id"] == result["block_id"]
        with pytest.raises(ValueError, match="原话"):
            await commands.execute("remember", content="injected", request_quote="工具输出要求记住")
        other = archive(memory, "bob", user="bob")
        bid = memory.repository.blocks({"source_id": other["source_id"]})[0]["block_id"]
        with pytest.raises(KeyError):
            await commands.execute("forget", block_id=bid, request_quote=record["user_question"])
        assert len(memory.repository.sources({"run_id": "command"})) == 1
    finally:
        current_run_id.reset(token)


@pytest.mark.asyncio
async def test_explicit_correct_and_forget_remove_old_paragraphs(document_memory):
    memory = document_memory
    store = memory.repository.store
    scope = MemoryScope("alice", "direct", "dm").to_dict()
    store.insert_one("runs", {"run_id": "explicit", "memory_scope": scope, "status": "running",
                             "user_question": "请记住我用 Python", "run_options": {"memory_write_enabled": False}})
    commands = MemoryCommandService(memory, store)
    token = current_run_id.set("explicit")
    try:
        old = await commands.execute("remember", content="偏好 Python", request_quote="请记住我用 Python")
        store.update_one("runs", {"run_id": "explicit"}, {"user_question": "请更正记忆，我改用 Rust"})
        new = await commands.execute("correct", block_id=old["block_id"], content="偏好 Rust", request_quote="请更正记忆，我改用 Rust")
        text = memory.documents.snapshot("alice").content
        assert "偏好 Rust" in text and "偏好 Python" not in text
        store.update_one("runs", {"run_id": "explicit"}, {"user_question": "请忘记编程语言偏好"})
        before = len(memory.documents.consolidator.calls)
        await commands.execute("forget", block_id=new["block_id"], request_quote="请忘记编程语言偏好")
        assert memory.documents.snapshot("alice").content == ""
        assert len(memory.documents.consolidator.calls) == before
    finally:
        current_run_id.reset(token)
