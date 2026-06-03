"""Coding agent 内联产物（inline artifact）接入。

设计边界（重要）：
  coding agent（Claude Code / Codex）是独立子进程，跑自己的 agent loop，
  **没有任何通道回到 agent_flow 的 bus / 工具调用协议**。因此它无法直接调用
  agent_flow 的 `inline_artifact` 工具。

  接入方式是"标记协议"：
    1. ArtifactProtocolProvider 把协议说明拼进 coding agent 的 prompt，
       告诉模型用 @@ARTIFACT_BEGIN@@ .. @@ARTIFACT_END@@ 包裹一个 JSON 产物。
    2. CodingExecutorAgent 在 im_backend 侧解析模型输出流里的标记块，复用
       agent_flow 的 InlineArtifactTool 构造产物 payload，再通过既有的
       EventStreamService 直接发出 `artifacts.<type>` 事件（与 native agent
       走 FrontendEventBridge.mirror_tool_event 得到的形状完全一致）。

  本模块只负责"协议说明文本"与"标记解析"，不直接产生事件——产物事件由
  executor 持有 run_id/agent_id 后统一发出。
"""

from __future__ import annotations

import json
from typing import Any

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()

# 协议说明文本与 ArtifactProtocolProvider 现已收敛到 agent_flow（domain.context.providers），
# 使 ContextService 能按 provider_id="artifact_protocol" 构建该 provider；这里仅 re-export
# 以保持既有导入路径不变。ARTIFACT_BEGIN/ARTIFACT_END 同样从 agent_flow 取，供下方解析器使用。
from domain.context.providers import (  # type: ignore  # noqa: E402
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    ARTIFACT_PROTOCOL_INSTRUCTION,
    ArtifactProtocolProvider,
)

__all__ = [
    "ARTIFACT_BEGIN",
    "ARTIFACT_END",
    "ARTIFACT_PROTOCOL_INSTRUCTION",
    "ArtifactProtocolProvider",
    "ArtifactStreamParser",
]


class ArtifactStreamParser:
    """从 coding agent 的文本流里提取产物标记块。

    支持标记被拆分到多个流式分片：内部维护缓冲，仅在拿到完整 END 时产出。
    feed() 返回 (可安全转发给前端的纯文本, [marker_dict, ...])。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_artifact = False
        self._artifact_buf = ""

    def feed(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        if text:
            self._buf += text
        clean_parts: list[str] = []
        markers: list[dict[str, Any]] = []
        while True:
            if not self._in_artifact:
                idx = self._buf.find(ARTIFACT_BEGIN)
                if idx == -1:
                    safe, self._buf = self._hold_partial(self._buf, ARTIFACT_BEGIN)
                    if safe:
                        clean_parts.append(safe)
                    break
                if idx:
                    clean_parts.append(self._buf[:idx])
                self._buf = self._buf[idx + len(ARTIFACT_BEGIN):]
                self._in_artifact = True
                self._artifact_buf = ""
            else:
                idx = self._buf.find(ARTIFACT_END)
                if idx == -1:
                    safe, self._buf = self._hold_partial(self._buf, ARTIFACT_END)
                    self._artifact_buf += safe
                    break
                self._artifact_buf += self._buf[:idx]
                self._buf = self._buf[idx + len(ARTIFACT_END):]
                self._in_artifact = False
                marker = self._parse(self._artifact_buf)
                if marker is not None:
                    markers.append(marker)
                self._artifact_buf = ""
        return "".join(clean_parts), markers

    def flush(self) -> tuple[str, list[dict[str, Any]]]:
        """流结束时调用：冲刷残留缓冲。未闭合的标记块尽力解析，否则丢弃。"""
        markers: list[dict[str, Any]] = []
        if self._in_artifact:
            marker = self._parse(self._artifact_buf)
            if marker is not None:
                markers.append(marker)
            self._in_artifact = False
            self._artifact_buf = ""
            self._buf = ""
            return "", markers
        clean, self._buf = self._buf, ""
        return clean, markers

    @staticmethod
    def _hold_partial(buf: str, sentinel: str) -> tuple[str, str]:
        """把可能是 sentinel 前缀的尾巴留在缓冲，其余作为安全文本返回。"""
        max_keep = min(len(sentinel) - 1, len(buf))
        for n in range(max_keep, 0, -1):
            if buf.endswith(sentinel[:n]):
                return buf[:-n], buf[-n:]
        return buf, ""

    @staticmethod
    def _parse(raw: str) -> dict[str, Any] | None:
        text = raw.strip()
        if not text:
            return None
        try:
            marker = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(marker, dict) or not marker.get("artifact_type"):
            return None
        return marker
