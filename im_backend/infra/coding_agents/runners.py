from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, Iterable

from im_backend.domain.models import CodingAgentEvent


class CodingAgentRunner(ABC):
    agent_kind: str
    prompt_via_stdin = False

    @abstractmethod
    def build_command(
        self,
        *,
        prompt: str,
        workdir: str,
        attachments: list[str] | None = None,
        permission_profile: str = "",
    ) -> list[str]:
        raise NotImplementedError

    async def run(
        self,
        *,
        prompt: str,
        workdir: str,
        attachments: list[str] | None = None,
        permission_profile: str = "",
    ) -> AsyncIterator[CodingAgentEvent]:
        command = self.build_command(
            prompt=prompt,
            workdir=workdir,
            attachments=attachments or [],
            permission_profile=permission_profile,
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workdir or None,
            stdin=asyncio.subprocess.PIPE if self.prompt_via_stdin else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if self.prompt_via_stdin:
            assert process.stdin is not None
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
        assert process.stdout is not None
        assert process.stderr is not None

        async for line in process.stdout:
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            for event in self.parse_line(text):
                yield event

        stderr = (await process.stderr.read()).decode("utf-8", errors="replace").strip()
        return_code = await process.wait()
        if return_code != 0:
            yield CodingAgentEvent(
                type="agent.failed",
                payload={
                    "return_code": return_code,
                    "stderr": stderr,
                    "command": command,
                },
            )

    def parse_line(self, line: str) -> Iterable[CodingAgentEvent]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return [CodingAgentEvent(type="agent.delta", payload={"delta": line})]
        return self.parse_json_event(data)

    def parse_json_event(self, data: dict) -> Iterable[CodingAgentEvent]:
        text = self._extract_text(data)
        if not text:
            return [CodingAgentEvent(type="agent.delta", payload={"raw": data})]
        return [CodingAgentEvent(type="agent.delta", payload={"delta": text, "raw": data})]

    def _extract_text(self, data: dict) -> str:
        for key in ("text", "content", "message", "delta"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        for key in ("item", "delta", "message"):
            value = data.get(key)
            if isinstance(value, dict):
                text = self._extract_text(value)
                if text:
                    return text
        content = data.get("content")
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}
            ]
            return "".join(parts)
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}
                ]
                return "".join(parts)
        return ""


class ClaudeCodeRunner(CodingAgentRunner):
    agent_kind = "claude_code"
    prompt_via_stdin = True

    def build_command(
        self,
        *,
        prompt: str,
        workdir: str,
        attachments: list[str] | None = None,
        permission_profile: str = "",
    ) -> list[str]:
        command = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            self._permission_mode(permission_profile),
            "--add-dir",
            str(Path(workdir).expanduser().resolve()),
        ]
        for attachment in attachments or []:
            command.extend(["--file", attachment])
        return command

    def _permission_mode(self, permission_profile: str) -> str:
        if permission_profile == "plan":
            return "plan"
        if permission_profile in {"acceptEdits", "auto", "bypassPermissions", "default", "dontAsk"}:
            return permission_profile
        return "acceptEdits"

    def parse_json_event(self, data: dict) -> Iterable[CodingAgentEvent]:
        event_type = data.get("type", "")
        if event_type in {"assistant", "content_block_delta"}:
            text = self._extract_text(data)
            return [CodingAgentEvent(type="agent.delta", payload={"delta": text, "raw": data})] if text else []
        if event_type in {"result", "final"}:
            return [CodingAgentEvent(type="agent.final", payload={"final": self._extract_text(data), "raw": data})]
        if event_type in {"tool_use", "tool_result"}:
            return [CodingAgentEvent(type="tool.called", payload={"raw": data})]
        return super().parse_json_event(data)


class CodexRunner(CodingAgentRunner):
    agent_kind = "codex"

    def build_command(
        self,
        *,
        prompt: str,
        workdir: str,
        attachments: list[str] | None = None,
        permission_profile: str = "",
    ) -> list[str]:
        sandbox, approval_policy, bypass = self._permission_config(permission_profile)
        command = [
            "codex",
            "exec",
            "--json",
            "-C",
            str(Path(workdir).expanduser().resolve()),
            "--skip-git-repo-check",
        ]
        if bypass:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            command.extend(["--sandbox", sandbox])
            command.extend(["-c", f"approval_policy={json.dumps(approval_policy)}"])
        for attachment in attachments or []:
            command.extend(["--image", attachment])
        command.append(prompt)
        return command

    def _permission_config(self, permission_profile: str) -> tuple[str, str, bool]:
        if permission_profile == "plan":
            return "read-only", "never", False
        if permission_profile in {"acceptEdits", "auto", "dontAsk"}:
            return "workspace-write", "never", False
        if permission_profile == "bypassPermissions":
            return "danger-full-access", "never", True
        if permission_profile == "default":
            return "workspace-write", "on-failure", False
        return "workspace-write", "on-request", False

    def parse_json_event(self, data: dict) -> Iterable[CodingAgentEvent]:
        event_type = data.get("type", data.get("event", ""))
        if event_type == "item.completed":
            item = data.get("item")
            item_type = item.get("type", "") if isinstance(item, dict) else ""
            text = self._extract_text(data)
            if item_type == "agent_message":
                return [CodingAgentEvent(type="agent.final", payload={"final": text, "raw": data})] if text else []
            if item_type in {"command_execution", "tool_call", "function_call", "mcp_tool_call"}:
                return [CodingAgentEvent(type="tool.called", payload={"raw": data})]
            return [CodingAgentEvent(type="agent.delta", payload={"delta": text, "raw": data})] if text else []
        if event_type in {"agent_message_delta", "message_delta", "response.output_text.delta"}:
            return [CodingAgentEvent(type="agent.delta", payload={"delta": self._extract_text(data), "raw": data})]
        if event_type in {"agent_message", "message", "response.completed", "final"}:
            return [CodingAgentEvent(type="agent.final", payload={"final": self._extract_text(data), "raw": data})]
        if event_type in {"exec_command_begin", "exec_command_end", "tool_call"}:
            return [CodingAgentEvent(type="tool.called", payload={"raw": data})]
        if event_type in {"thread.started", "turn.started", "turn.completed", "item.started", "item.updated"}:
            return []
        return super().parse_json_event(data)


def runner_for_kind(agent_kind: str) -> CodingAgentRunner | None:
    if agent_kind == "claude_code":
        return ClaudeCodeRunner()
    if agent_kind == "codex":
        return CodexRunner()
    return None
