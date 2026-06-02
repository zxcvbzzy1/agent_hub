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

from domain.context.providers import ContextProvider  # type: ignore  # noqa: E402


ARTIFACT_BEGIN = "@@ARTIFACT_BEGIN@@"
ARTIFACT_END = "@@ARTIFACT_END@@"


ARTIFACT_PROTOCOL_INSTRUCTION = (
    "## 内联产物协议\n"
    "当你需要向用户展示一个“产物”（代码改动对比、可预览文档/文件、图片、网页预览，"
    "或一条结构化消息）时，在正文中单独输出一个产物标记块。系统会捕获该标记块、"
    "渲染成内联卡片，并自动把标记本身从展示文本里移除。\n\n"
    "重要：你不能直接调用 agent_flow 的 inline_artifact 工具；Claude Code / Codex 的"
    "shell 命令、文件读取、command_execution 输出也不会自动变成产物。若要让前端出现"
    "产物卡片，必须由你在最终回复文本中原样输出下面的标记块。\n\n"
    "标记块格式（起止标记各占一行，中间是一个合法 JSON 对象）：\n\n"
    f"{ARTIFACT_BEGIN}\n"
    '{"artifact_type": "<类型>", "<类型>": { ...该类型字段... }}\n'
    f"{ARTIFACT_END}\n\n"
    "artifact_type 取值与对应字段：\n"
    '- message  普通消息：{"title","content","mime_type"?,"metadata"?}\n'
    '- image    图片：{"title","url","alt"?,"mime_type"?,"metadata"?}\n'
    '- diff     代码改动对比：{"title","before","after","file_path"?,"language"?,"metadata"?}\n'
    '- document 可预览文档/文件：{"title","content","format"?(md/py/js/json/txt...),"language"?,"editable"?,"metadata"?}\n'
    '- web      网页预览：{"title","url"?,"html"?,"preview_title"?,"metadata"?}\n\n'
    "规则：\n"
    "- JSON 必须合法、可一次性解析；顶层只放 artifact_type 与同名的类型对象；"
    "content/before/after/html 内的换行必须写成 JSON 字符串里的 \\n 转义，不能放未转义的真实换行。\n"
    "- 一次只放一个产物；要展示多个产物就输出多个标记块。\n"
    "- 用户要求展示、预览、生成、创建、打开某个文件内容时，读取/生成内容后必须输出 "
    "document 产物标记块；title 使用文件名或简短标题，content 放完整可展示内容，"
    "format/language 按文件扩展名填写，editable 通常设为 true。\n"
    "- 用户要求展示代码修改前后对比时，必须输出 diff 产物标记块。\n"
    "- 不要把 shell 命令输出当作已经完成产物展示；命令只用于获取内容，产物展示必须靠标记块。\n"
    "- 仅在确有产物要展示时使用；普通解释照常直接输出，不要包进标记。\n"
    "- 标记块之外的正文会照常流式展示给用户。\n"
)


class ArtifactProtocolProvider(ContextProvider):
    """把内联产物协议说明注入 coding agent 的上下文。

    只注入说明文本——产物事件由 executor 解析标记后发出。
    """

    name = "artifact_protocol"

    def get(self, state: dict) -> list[str]:
        return [ARTIFACT_PROTOCOL_INSTRUCTION]


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
