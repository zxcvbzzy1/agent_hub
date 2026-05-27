from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import MessageStatus, SenderType, new_id, now_ts
from im_backend.domain.content import ContentPart


@dataclass
class Message:
    message_id: str
    sender_type: SenderType
    sender_id: str
    content_parts: list[ContentPart]
    room_id: str = ""
    conversation_id: str = ""
    mentions: list[str] = field(default_factory=list)
    reply_to: str = ""
    quote_of: str = ""
    run_id: str = ""
    status: MessageStatus = "sent"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    @classmethod
    def create(
        cls,
        *,
        sender_type: SenderType,
        sender_id: str,
        content_parts: list[ContentPart],
        room_id: str = "",
        conversation_id: str = "",
        mentions: list[str] | None = None,
        reply_to: str = "",
        quote_of: str = "",
        run_id: str = "",
        status: MessageStatus = "sent",
        metadata: dict[str, Any] | None = None,
    ) -> "Message":
        if not room_id and not conversation_id:
            raise ValueError("message 必须归属 room 或 conversation")
        return cls(
            message_id=new_id(),
            sender_type=sender_type,
            sender_id=sender_id,
            content_parts=content_parts,
            room_id=room_id,
            conversation_id=conversation_id,
            mentions=mentions or [],
            reply_to=reply_to,
            quote_of=quote_of,
            run_id=run_id,
            status=status,
            metadata=metadata or {},
        )

    def text_content(self) -> str:
        chunks: list[str] = []
        for part in self.content_parts:
            if part.type in {"text", "code"} and part.text:
                chunks.append(part.text)
            elif part.type == "diff" and part.diff:
                chunks.append(part.diff)
        return "\n\n".join(chunks).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "room_id": self.room_id,
            "conversation_id": self.conversation_id,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "content_parts": [part.to_dict() for part in self.content_parts],
            "mentions": self.mentions,
            "reply_to": self.reply_to,
            "quote_of": self.quote_of,
            "run_id": self.run_id,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
