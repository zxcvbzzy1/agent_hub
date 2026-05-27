from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import ActionType, new_id, now_ts


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

