from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


RoomType = Literal["dm", "group"]
SenderType = Literal["user", "agent", "system"]
ContentPartType = Literal[
    "text",
    "code",
    "image",
    "file",
    "web_preview",
    "diff",
    "deploy",
    "event_ref",
]
MessageStatus = Literal["pending", "sent", "running", "finished", "failed", "cancelled"]
ActionType = Literal["reply", "quote", "copy", "expand", "apply_diff", "approve", "reject"]
AgentKind = Literal["native", "claude_code", "codex", "human_proxy"]


def new_id() -> str:
    return str(uuid.uuid4())


def now_ts() -> float:
    return time.time()


@dataclass
class ContentPart:
    type: ContentPartType
    text: str = ""
    language: str = ""
    url: str = ""
    name: str = ""
    mime_type: str = ""
    size: int = 0
    artifact_id: str = ""
    diff: str = ""
    title: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentPart":
        return cls(
            type=data.get("type", "text"),
            text=data.get("text", ""),
            language=data.get("language", ""),
            url=data.get("url", ""),
            name=data.get("name", ""),
            mime_type=data.get("mime_type", ""),
            size=int(data.get("size", 0) or 0),
            artifact_id=data.get("artifact_id", ""),
            diff=data.get("diff", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}) or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "language": self.language,
            "url": self.url,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
            "artifact_id": self.artifact_id,
            "diff": self.diff,
            "title": self.title,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class Room:
    room_id: str
    type: RoomType
    title: str
    member_agent_ids: list[str] = field(default_factory=list)
    created_by: str = "user"
    avatar_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    @classmethod
    def create(
        cls,
        *,
        type: RoomType,
        title: str,
        member_agent_ids: list[str],
        created_by: str = "user",
        avatar_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "Room":
        return cls(
            room_id=new_id(),
            type=type,
            title=title or ("单聊" if type == "dm" else "群聊"),
            member_agent_ids=member_agent_ids,
            created_by=created_by,
            avatar_url=avatar_url,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "type": self.type,
            "title": self.title,
            "member_agent_ids": self.member_agent_ids,
            "created_by": self.created_by,
            "avatar_url": self.avatar_url,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Message:
    message_id: str
    room_id: str
    sender_type: SenderType
    sender_id: str
    content_parts: list[ContentPart]
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
        room_id: str,
        sender_type: SenderType,
        sender_id: str,
        content_parts: list[ContentPart],
        mentions: list[str] | None = None,
        reply_to: str = "",
        quote_of: str = "",
        run_id: str = "",
        status: MessageStatus = "sent",
        metadata: dict[str, Any] | None = None,
    ) -> "Message":
        return cls(
            message_id=new_id(),
            room_id=room_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content_parts=content_parts,
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


@dataclass
class MessageAction:
    action_id: str
    message_id: str
    action_type: ActionType
    actor_id: str = "user"
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "recorded"
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    @classmethod
    def create(
        cls,
        *,
        message_id: str,
        action_type: ActionType,
        actor_id: str = "user",
        payload: dict[str, Any] | None = None,
        status: str = "recorded",
    ) -> "MessageAction":
        return cls(
            action_id=new_id(),
            message_id=message_id,
            action_type=action_type,
            actor_id=actor_id,
            payload=payload or {},
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "message_id": self.message_id,
            "action_type": self.action_type,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AgentRuntimeProfile:
    agent_id: str
    agent_kind: AgentKind = "native"
    avatar_url: str = ""
    capabilities: list[str] = field(default_factory=list)
    workdir: str = ""
    permission_profile: str = "human_confirm"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_agent_record(cls, record: dict[str, Any]) -> "AgentRuntimeProfile":
        metadata = record.get("metadata", {}) or {}
        return cls(
            agent_id=record.get("agent_id", ""),
            agent_kind=metadata.get("agent_kind", "native"),
            avatar_url=metadata.get("avatar_url", ""),
            capabilities=metadata.get("capabilities", []) or [],
            workdir=metadata.get("workdir", ""),
            permission_profile=metadata.get("permission_profile", "human_confirm"),
            metadata=metadata,
        )


@dataclass
class CodingAgentEvent:
    type: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "created_at": self.created_at,
        }
