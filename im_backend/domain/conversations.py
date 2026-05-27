from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import new_id, now_ts


@dataclass
class Conversation:
    conversation_id: str
    agent_id: str
    title: str
    created_by: str = "user"
    avatar_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        title: str,
        created_by: str = "user",
        avatar_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "Conversation":
        return cls(
            conversation_id=new_id(),
            agent_id=agent_id,
            title=title or "新对话",
            created_by=created_by,
            avatar_url=avatar_url,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "created_by": self.created_by,
            "avatar_url": self.avatar_url,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
