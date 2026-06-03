from __future__ import annotations

from typing import Any, Callable


def history_before(
    messages: list[dict[str, Any]],
    before_message_id: str,
    *,
    require_text: Callable[[dict[str, Any]], Any] | None = None,
    tail: int | None = None,
) -> list[dict[str, Any]]:
    """取 before_message_id 之前的 user/agent 消息作为历史窗口。

    接收已查好的消息列表（不在此访问 store）。差异以参数表达：
      require_text: 仅保留该函数返回真值的消息（如过滤空文本，群聊用）。
      tail:         只保留最后 N 条（群聊用 15；单聊不截尾）。
    """
    history: list[dict[str, Any]] = []
    for message in messages:
        if message.get("message_id") == before_message_id:
            break
        if message.get("sender_type") not in {"user", "agent"}:
            continue
        if message.get("status") == "cancelled":
            continue
        if require_text is not None and not require_text(message):
            continue
        history.append(message)
    if tail is not None:
        return history[-tail:]
    return history
