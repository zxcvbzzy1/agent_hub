from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from im_backend.domain.common import new_id, now_ts

FavoriteScope = Literal["conversation", "room"]


@dataclass
class Favorite:
    """用户收藏的关键信息，作为某个会话/群聊的长期固定上下文。"""

    favorite_id: str
    scope_type: FavoriteScope
    scope_id: str
    content: str
    title: str = ""
    source_message_id: str = ""
    enabled: bool = True
    created_by: str = "user"
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    @classmethod
    def create(
        cls,
        *,
        scope_type: FavoriteScope,
        scope_id: str,
        content: str,
        title: str = "",
        source_message_id: str = "",
        enabled: bool = True,
        created_by: str = "user",
    ) -> "Favorite":
        if scope_type not in ("conversation", "room"):
            raise ValueError("scope_type 必须是 conversation 或 room")
        if not scope_id:
            raise ValueError("scope_id 不能为空")
        if not (content or "").strip():
            raise ValueError("收藏内容不能为空")
        return cls(
            favorite_id=new_id(),
            scope_type=scope_type,
            scope_id=scope_id,
            content=content.strip(),
            title=title.strip(),
            source_message_id=source_message_id,
            enabled=enabled,
            created_by=created_by,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "favorite_id": self.favorite_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "content": self.content,
            "title": self.title,
            "source_message_id": self.source_message_id,
            "enabled": self.enabled,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
