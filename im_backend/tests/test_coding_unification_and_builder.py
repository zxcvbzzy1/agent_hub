"""coding agent 上下文统一（provider 化 + DB 模版）与对话式创建（AgentBuilder）的回归测试。"""

from __future__ import annotations

import asyncio
import time
import pytest
from im_backend.tests.test_redis_im_integration import backend

from fastapi.testclient import TestClient

from im_backend.api.core import get_container
from im_backend.api.index import app
from im_backend.application.services.messaging.agent_builder import AgentBuilderService
from im_backend.domain.models import CodingAgentEvent


def _auth_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/im/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "agent-flow", "display_name": username},
    )
    if response.status_code != 200:
        response = client.post("/api/im/auth/login", json={"username": username, "password": "agent-flow"})
    return {"Authorization": f"Bearer {response.json()['item']['token']}"}


_ARTIFACT_DELTA = (
    "处理完成。\n"
    "@@ARTIFACT_BEGIN@@\n"
    '{"artifact_type": "document", "document": {"title": "result.txt", "content": "hello world"}}\n'
    "@@ARTIFACT_END@@\n"
)


class _ArtifactCodingRunner:
    """记录最终 prompt，并产出一个内联产物标记块。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def run(self, *, prompt: str, workdir: str, attachments=None, permission_profile: str = ""):
        self.prompts.append(prompt)
        yield CodingAgentEvent(type="agent.delta", payload={"delta": _ARTIFACT_DELTA})
        yield CodingAgentEvent(type="agent.final", payload={"final": "处理完成。"})


# ── 工作流 A：coding 上下文模版 ───────────────────────────────────────


def test_default_coding_context_seeded_with_expected_providers(backend):
    container = backend[0]
    ctx = container.bridge.contexts.get_context("default_coding")
    assert ctx is not None
    assert ctx.get("kind") == "coding"
    assert ctx.get("provider_names") == [
        "user_prompt",
        "pinned_context",
        "skill",
        "artifact_protocol",
        "history",
    ]


def test_coding_engine_injects_prompt_pinned_and_artifact_protocol(backend):
    container = backend[0]
    engine = container.bridge.contexts.get_engine("default_coding")
    built = engine.build({"prompt": "写个脚本", "pinned_context": ["记住：用 pytest"]})
    assert "写个脚本" in built
    assert "记住：用 pytest" in built
    assert "内联产物协议" in built


def test_coding_provider_config_round_trip_preserves_artifact_protocol(backend):
    container = backend[0]
    ctxsvc = container.bridge.contexts
    rec = ctxsvc.create_context(kind="coding", name="rt", provider_config=ctxsvc.default_template("coding"))
    engine = ctxsvc.get_engine(rec["context_id"])
    rt = ctxsvc.create_context_from_engine(kind="coding", name="rt2", engine=engine)
    provider_ids = [item["provider_id"] for item in rt["provider_config"]]
    assert "artifact_protocol" in provider_ids


def test_create_coding_agent_gets_private_coding_context(backend):
    container = backend[0]
    agent = container.im.create_agent(
        name="私有 Codex",
        agent_type="executor",
        metadata={"agent_kind": "codex"},
        owner_user_id="owner-1",
    )
    context_id = agent["context_id"]
    assert context_id not in ("default_executor", "default_coding")
    ctx = container.bridge.contexts.get_context(context_id)
    assert ctx.get("kind") == "coding"


@pytest.mark.asyncio
async def test_dm_coding_reply_uses_provider_path_and_collects_artifact(monkeypatch, backend):
    _, client, headers = backend
    container = backend[0]

    runner = _ArtifactCodingRunner()
    monkeypatch.setattr(
        "im_backend.infra.coding_agents.executor_agent.runner_for_kind",
        lambda agent_kind: runner,
    )

    agent = (await client.post(
        "/api/im/agents",
        json={
            "name": "DM Claude",
            "agent_type": "executor",
            "metadata": {"agent_kind": "claude_code", "description": "coding"},
        },
        headers=headers,
    )).json()["item"]
    agent_id = agent["agent_id"]

    conversation = (await client.post(
        f"/api/im/agents/{agent_id}/conversations",
        json={"title": "coding dm"},
        headers=headers,
    )).json()["item"]
    conversation_id = conversation["conversation_id"]

    # 一条会话级收藏 -> 应通过 pinned_context provider 进入 coding agent 上下文。
    await container.im.create_favorite(
        scope_type="conversation",
        scope_id=conversation_id,
        content="记住：始终用 pytest",
        title="约定",
    )

    user_message = (await client.post(
        f"/api/im/conversations/{conversation_id}/messages",
        json={"sender_type": "user", "content_parts": [{"type": "text", "text": "跑一下测试"}]},
        headers=headers,
    )).json()["item"]
    await client.post(
        f"/api/im/conversations/{conversation_id}/reply",
        json={"message_id": user_message["message_id"], "auto_start": True},
        headers=headers,
    )

    agent_messages: list = []
    for _ in range(40):
        messages = (await client.get(f"/api/im/conversations/{conversation_id}/messages")).json()["items"]
        agent_messages = [item for item in messages if item.get("sender_type") == "agent"]
        if agent_messages:
            break
        await asyncio.sleep(0.05)

    assert agent_messages, "coding DM 未产生 agent 回复"
    reply = agent_messages[-1]
    # 走的是统一的 native provider 路径（_run_reply_task），而非已删除的 direct_coding_agent 分支。
    assert reply["metadata"]["source"] == "direct_agent_reply"
    assert reply["metadata"]["reply_to"] == user_message["message_id"]
    # 内联产物被收集成 content_part。
    assert any(part.get("type") == "artifact" for part in reply["content_parts"])

    # 最终喂给 runner 的 prompt 来自 ContextEngine：含产物协议 + 收藏(pinned) + 用户诉求。
    assert runner.prompts
    prompt = runner.prompts[0]
    assert "内联产物协议" in prompt
    assert "始终用 pytest" in prompt
    assert "跑一下测试" in prompt


# ── 工作流 C：AgentBuilder ───────────────────────────────────────────


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    async def chat(self, messages):  # noqa: ANN001
        return self.text


def test_agent_builder_returns_merged_draft_and_strips_fence(backend):
    container = backend[0]
    fake = _FakeLLM(
        "好的，建一个前端工程师。\n```json\n"
        '{"name": "前端工程师", "agent_kind": "native", "agent_type": "executor", "ready": true}\n```'
    )
    svc = AgentBuilderService(agents=container.agents, llm=fake)
    result = asyncio.run(svc.chat(messages=[{"role": "user", "content": "做个写前端的"}], draft=None))
    assert "```" not in result["reply"]
    assert result["draft"]["name"] == "前端工程师"
    assert result["draft"]["agent_kind"] == "native"
    assert result["ready"] is True


def test_agent_builder_malformed_json_keeps_prior_draft(backend):
    container = backend[0]
    fake = _FakeLLM("再想想\n```json\n{name: 没引号,}\n```")
    svc = AgentBuilderService(agents=container.agents, llm=fake)
    prior = {"name": "保留我", "agent_kind": "codex"}
    result = asyncio.run(svc.chat(messages=[{"role": "user", "content": "hi"}], draft=prior))
    assert result["ready"] is False
    assert result["draft"]["name"] == "保留我"
    assert result["draft"]["agent_kind"] == "codex"
    assert result["draft"]["agent_type"] == "executor"  # 非 native 钳制为 executor


def test_agent_builder_clamps_invalid_combination(backend):
    container = backend[0]
    fake = _FakeLLM(
        'ok\n```json\n{"name": "X", "agent_kind": "codex", "agent_type": "planner", "tool_names": ["a"], "ready": true}\n```'
    )
    svc = AgentBuilderService(agents=container.agents, llm=fake)
    result = asyncio.run(svc.chat(messages=[{"role": "user", "content": "hi"}], draft=None))
    assert result["draft"]["agent_type"] == "executor"
    assert result["draft"]["tool_names"] == []  # 非 native+executor 丢弃工具
