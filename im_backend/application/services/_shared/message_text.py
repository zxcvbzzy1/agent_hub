from __future__ import annotations

from typing import Any

from im_backend.domain.models import ContentPart, Message


def message_text(message: dict[str, Any]) -> str:
    """从消息 dict 提取纯文本（text/code/diff 部分）。

    之前 GroupMessageService.message_text / ConversationService._message_text /
    FavoriteService._message_text 三处逐字相同，统一收敛到此。保留对 message_id 等
    必需键的同样取值方式，不改变缺字段时的 KeyError 行为。
    """
    parts = [ContentPart.from_dict(part) for part in message.get("content_parts", [])]
    return Message(
        message_id=message["message_id"],
        room_id=message.get("room_id", ""),
        conversation_id=message.get("conversation_id", ""),
        sender_type=message["sender_type"],
        sender_id=message["sender_id"],
        content_parts=parts,
    ).text_content()
