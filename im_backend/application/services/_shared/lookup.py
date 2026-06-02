from __future__ import annotations

from typing import Any


def find_im_message(store, message_id: str) -> dict[str, Any] | None:
    """按 id 反查 im_messages，找不到返回 None（用于 reply/quote 引用解析）。"""
    return store.find_one("im_messages", {"message_id": message_id})


def require_im_message(store, message_id: str) -> dict[str, Any]:
    """按 id 取 im_messages，找不到抛 KeyError（统一各 service 的 get_message 行为）。"""
    message = find_im_message(store, message_id)
    if message is None:
        raise KeyError(f"消息不存在: {message_id}")
    return message
