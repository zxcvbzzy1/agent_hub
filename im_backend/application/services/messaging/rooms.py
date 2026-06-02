from __future__ import annotations

from typing import Any

from im_backend.application.services.platform.cleanup import IMCleanupService
from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.domain.models import Room
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class RoomService:
    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        events: RoomEventStreamService,
        cleanup: IMCleanupService,
        agents: IMAgentService,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._cleanup = cleanup
        self._agents = agents

    def create_room(
        self,
        *,
        type: str,
        title: str = "",
        member_agent_ids: list[str] | None = None,
        created_by: str = "user",
        avatar_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        member_agent_ids = member_agent_ids or []
        if type not in {"dm", "group"}:
            raise ValueError("room type 必须是 dm 或 group")
        if type != "group":
            raise ValueError("room 只用于 agent 群聊；单聊请创建 conversation")
        for agent_id in member_agent_ids:
            self._agents.ensure_agent_access(agent_id, created_by)

        room_metadata = {
            "planner_agent_id": "default_planner",
            "orchestrator": "PlanOrchestrator",
            "execution_mode": "plan",
            **(metadata or {}),
        }
        planner_agent_id = room_metadata.get("planner_agent_id")
        if planner_agent_id:
            planner = self._agents.ensure_agent_access(planner_agent_id, created_by)
            if planner.get("agent_type") != "planner":
                raise ValueError("planner_agent_id 必须指向 planner agent")

        room = Room.create(
            type=type,
            title=title,
            member_agent_ids=member_agent_ids,
            created_by=created_by,
            avatar_url=avatar_url,
            metadata=room_metadata,
        )
        record = self._store.insert_one("im_rooms", room.to_dict())
        self._events.publish(record["room_id"], "room.created", {"room": record})
        return record

    def list_rooms(self) -> list[dict[str, Any]]:
        return self._store.find_many("im_rooms", {"type": "group"}, sort=[("created_at", -1)])

    def get_room(self, room_id: str) -> dict[str, Any]:
        room = self._store.find_one("im_rooms", {"room_id": room_id})
        if room is None:
            raise KeyError(f"房间不存在: {room_id}")
        return room

    def update_room(
        self,
        room_id: str,
        *,
        title: str | None = None,
        avatar_url: str | None = None,
        member_agent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        room = self.get_room(room_id)
        if room.get("type") != "group":
            raise ValueError("只有群聊 room 支持更新")
        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if avatar_url is not None:
            updates["avatar_url"] = avatar_url
        if member_agent_ids is not None:
            for agent_id in member_agent_ids:
                if user_id:
                    self._agents.ensure_agent_access(agent_id, user_id)
                else:
                    self._bridge.ensure_agent_exists(agent_id)
            updates["member_agent_ids"] = member_agent_ids
        if metadata is not None:
            next_metadata = {**(room.get("metadata") or {}), **metadata}
            planner_agent_id = next_metadata.get("planner_agent_id")
            if planner_agent_id:
                planner = (
                    self._agents.ensure_agent_access(planner_agent_id, user_id)
                    if user_id
                    else self._bridge.ensure_agent_exists(planner_agent_id)
                )
                if planner.get("agent_type") != "planner":
                    raise ValueError("planner_agent_id 必须指向 planner agent")
            updates["metadata"] = next_metadata
        if not updates:
            return room
        record = self._store.update_one("im_rooms", {"room_id": room_id}, updates)
        self._events.publish(room_id, "room.updated", {"room": record})
        return record or self.get_room(room_id)

    def delete_room(self, room_id: str) -> dict[str, Any]:
        room = self.get_room(room_id)
        if room.get("type") != "group":
            raise ValueError("room 删除只服务群聊")
        stats = self._cleanup.delete_room(room_id)
        return {"deleted": True, "room_id": room_id, "stats": stats}

    def ensure_group_room(self, room_id: str) -> dict[str, Any]:
        room = self.get_room(room_id)
        if room.get("type") != "group":
            raise ValueError("该接口只服务群聊 room")
        return room
