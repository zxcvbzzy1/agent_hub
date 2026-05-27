from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from im_backend.domain.common import RoomType, new_id, now_ts


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

