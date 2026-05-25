from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, Iterable

from im_backend.domain.models import CodingAgentEvent


class CodingAgentRunner(ABC):
    agent_kind: str

    @abstractmethod
    def build_command(self, *, prompt: str, workdir: str, attachments: list[str] | None = None) -> list[str]:
        raise NotImplementedError

    async def run(
        self,
        *,
        prompt: str,
        workdir: str,
        attachments: list[str] | None = None,
    ) -> AsyncIterator[CodingAgentEvent]:
        command = self.build_command(prompt=prompt, workdir=workdir, attachments=attachments or [])
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workdir or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
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
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
                ]
                return "".join(parts)
        return ""


class ClaudeCodeRunner(CodingAgentRunner):
    agent_kind = "claude_code"

    def build_command(self, *, prompt: str, workdir: str, attachments: list[str] | None = None) -> list[str]:
        command = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "plan",
            "--add-dir",
            str(Path(workdir).expanduser().resolve()),
        ]
        for attachment in attachments or []:
            command.extend(["--file", attachment])
        command.append(prompt)
        return command

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

    def build_command(self, *, prompt: str, workdir: str, attachments: list[str] | None = None) -> list[str]:
        command = [
            "codex",
            "exec",
            "--json",
            "-C",
            str(Path(workdir).expanduser().resolve()),
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
        ]
        for attachment in attachments or []:
            command.extend(["--image", attachment])
        command.append(prompt)
        return command

    def parse_json_event(self, data: dict) -> Iterable[CodingAgentEvent]:
        event_type = data.get("type", data.get("event", ""))
        if event_type in {"agent_message_delta", "message_delta", "response.output_text.delta"}:
            return [CodingAgentEvent(type="agent.delta", payload={"delta": self._extract_text(data), "raw": data})]
        if event_type in {"agent_message", "message", "response.completed", "final"}:
            return [CodingAgentEvent(type="agent.final", payload={"final": self._extract_text(data), "raw": data})]
        if event_type in {"exec_command_begin", "exec_command_end", "tool_call"}:
            return [CodingAgentEvent(type="tool.called", payload={"raw": data})]
        return super().parse_json_event(data)


def runner_for_kind(agent_kind: str) -> CodingAgentRunner | None:
    if agent_kind == "claude_code":
        return ClaudeCodeRunner()
    if agent_kind == "codex":
        return CodexRunner()
    return None
