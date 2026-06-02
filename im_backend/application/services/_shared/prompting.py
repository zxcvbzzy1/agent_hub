from __future__ import annotations

from typing import Any, Callable

# 被回复/引用的原消息可能很长，注入 prompt 时截断，避免淹没用户本条诉求。
REFERENCE_CLIP = 2000


def _clip(text: str, limit: int = REFERENCE_CLIP) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…（引用内容已截断）"


def _sender_label(message: dict[str, Any]) -> str:
    sender_type = message.get("sender_type")
    if sender_type == "user":
        return "用户"
    if sender_type == "system":
        return "系统"
    return f"Agent {message.get('sender_id', '')}".strip()


def compose_prompt_with_references(
    message: dict[str, Any],
    *,
    lookup: Callable[[str], dict[str, Any] | None],
    text_of: Callable[[dict[str, Any]], str],
) -> str:
    """把用户消息的 reply_to / quote_of 引用内容拼进 prompt。

    前端的"回复 / 引用"操作只在消息上记录 reply_to / quote_of（被引用消息 id），
    若不拼接，agent 收到的只有用户本条文本、看不到被回复/引用的上下文。这里按
    id 反查原消息并以带标签的引用块前置，让 agent 明确"在回应哪条消息"。

    lookup : message_id -> 消息 dict（None 表示找不到，跳过该引用）。
    text_of: 消息 dict -> 纯文本（复用各服务已有的 message_text 逻辑）。
    """
    body = text_of(message)
    blocks: list[str] = []
    for label, key in (("回复", "reply_to"), ("引用", "quote_of")):
        ref_id = message.get(key)
        if not ref_id:
            continue
        ref = lookup(ref_id)
        if not ref:
            continue
        ref_text = _clip(text_of(ref))
        if not ref_text:
            continue
        blocks.append(f"【{label} {_sender_label(ref)}】\n{ref_text}")
    if not blocks:
        return body
    return "\n\n".join(blocks) + f"\n\n【本条消息】\n{body}"
