from __future__ import annotations

from typing import Any

from im_backend.application.services.events import RoomEventStreamService
from im_backend.domain.models import ContentPart, Favorite, Message


class FavoriteService:
    """收藏 = 固定写入某个 conversation/room 的长期上下文。"""

    def __init__(self, *, store, events: RoomEventStreamService) -> None:
        self._store = store
        self._events = events

    # ── 查询 ──────────────────────────────────────────────────────
    def get_favorite(self, favorite_id: str) -> dict[str, Any]:
        record = self._store.find_one("im_favorites", {"favorite_id": favorite_id})
        if record is None:
            raise KeyError(f"收藏不存在: {favorite_id}")
        return record

    def list_favorites(self, *, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        return self._store.find_many(
            "im_favorites",
            {"scope_type": scope_type, "scope_id": scope_id},
            sort=[("created_at", 1)],
        )

    def context_items(self, scope_type: str, scope_id: str) -> list[str]:
        """返回 enabled 收藏的注入文本，供 PinnedContextProvider 使用。"""
        items: list[str] = []
        for favorite in self.list_favorites(scope_type=scope_type, scope_id=scope_id):
            if favorite.get("enabled", True) is False:
                continue
            content = (favorite.get("content") or "").strip()
            if not content:
                continue
            title = (favorite.get("title") or "").strip()
            items.append(f"「{title}」{content}" if title else content)
        return items

    # ── 写 ────────────────────────────────────────────────────────
    def create_favorite(
        self,
        *,
        scope_type: str,
        scope_id: str,
        content: str,
        title: str = "",
        source_message_id: str = "",
        created_by: str = "user",
    ) -> dict[str, Any]:
        self._ensure_scope_exists(scope_type, scope_id)
        favorite = Favorite.create(
            scope_type=scope_type,
            scope_id=scope_id,
            content=content,
            title=title,
            source_message_id=source_message_id,
            created_by=created_by,
        )
        record = self._store.insert_one("im_favorites", favorite.to_dict())
        self._events.publish(scope_id, "favorite.created", {"favorite": record})
        return record

    def favorite_message(self, *, message_id: str, title: str = "", created_by: str = "user") -> dict[str, Any]:
        message = self._store.find_one("im_messages", {"message_id": message_id})
        if message is None:
            raise KeyError(f"消息不存在: {message_id}")
        scope_type, scope_id = self._resolve_message_scope(message)
        content = self._message_text(message) or "(空消息)"
        return self.create_favorite(
            scope_type=scope_type,
            scope_id=scope_id,
            content=content,
            title=title,
            source_message_id=message_id,
            created_by=created_by,
        )

    def update_favorite(
        self,
        favorite_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        favorite = self.get_favorite(favorite_id)
        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title.strip()
        if content is not None:
            if not content.strip():
                raise ValueError("收藏内容不能为空")
            updates["content"] = content.strip()
        if enabled is not None:
            updates["enabled"] = bool(enabled)
        if not updates:
            return favorite
        record = self._store.update_one("im_favorites", {"favorite_id": favorite_id}, updates)
        record = record or self.get_favorite(favorite_id)
        self._events.publish(record["scope_id"], "favorite.updated", {"favorite": record})
        return record

    def delete_favorite(self, favorite_id: str) -> dict[str, Any]:
        favorite = self.get_favorite(favorite_id)
        self._store.delete_one("im_favorites", {"favorite_id": favorite_id})
        self._events.publish(favorite["scope_id"], "favorite.deleted", {"favorite_id": favorite_id})
        return {"deleted": True, "favorite_id": favorite_id}

    # ── 内部 ──────────────────────────────────────────────────────
    def _ensure_scope_exists(self, scope_type: str, scope_id: str) -> None:
        if scope_type == "conversation":
            if self._store.find_one("im_conversations", {"conversation_id": scope_id}) is None:
                raise KeyError(f"对话不存在: {scope_id}")
        elif scope_type == "room":
            if self._store.find_one("im_rooms", {"room_id": scope_id}) is None:
                raise KeyError(f"房间不存在: {scope_id}")
        else:
            raise ValueError("scope_type 必须是 conversation 或 room")

    def _resolve_message_scope(self, message: dict[str, Any]) -> tuple[str, str]:
        if message.get("room_id"):
            return "room", message["room_id"]
        if message.get("conversation_id"):
            return "conversation", message["conversation_id"]
        raise ValueError("消息既不属于 room 也不属于 conversation")

    def _message_text(self, message: dict[str, Any]) -> str:
        parts = [ContentPart.from_dict(part) for part in message.get("content_parts", [])]
        return Message(
            message_id=message["message_id"],
            room_id=message.get("room_id", ""),
            conversation_id=message.get("conversation_id", ""),
            sender_type=message["sender_type"],
            sender_id=message["sender_id"],
            content_parts=parts,
        ).text_content()
