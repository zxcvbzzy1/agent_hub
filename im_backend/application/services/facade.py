from __future__ import annotations

from pathlib import Path
from typing import Any

from im_backend.application.services.messaging.actions import MessageActionService
from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.platform.cleanup import IMCleanupService
from im_backend.application.services.orchestration.coding_agents import CodingAgentService
from im_backend.application.services.messaging.conversations import ConversationService
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.messaging.favorites import FavoriteService
from im_backend.application.services.messaging.messages import GroupMessageService
from im_backend.application.services.messaging.rooms import RoomService
from im_backend.application.services.orchestration.runs import GroupRunService
from im_backend.application.services.orchestration.runtime_reply import PlannerFinalReplyWriter
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class IMService:
    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        room_events: RoomEventStreamService,
        default_workdir: str | Path,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = room_events
        self.cleanup = IMCleanupService(store)
        self.favorites = FavoriteService(store=store, events=room_events)
        self.agents = IMAgentService(bridge=bridge, cleanup=self.cleanup)
        self.rooms = RoomService(store=store, bridge=bridge, events=room_events, cleanup=self.cleanup, agents=self.agents)
        self.messages = GroupMessageService(store=store, bridge=bridge, events=room_events, rooms=self.rooms, agents=self.agents)
        self.actions = MessageActionService(store=store, events=room_events)
        self.coding_agents = CodingAgentService(store=store, events=room_events, messages=self.messages)
        self.conversations = ConversationService(
            store=store,
            bridge=bridge,
            events=room_events,
            default_workdir=default_workdir,
            agents=self.agents,
            coding_agents=self.coding_agents,
            favorites=self.favorites,
            cleanup=self.cleanup,
        )
        self.runs = GroupRunService(
            store=store,
            bridge=bridge,
            events=room_events,
            rooms=self.rooms,
            messages=self.messages,
            coding_agents=self.coding_agents,
            agents=self.agents,
            favorites=self.favorites,
            default_workdir=default_workdir,
        )
        # planner 的最终回复落库成房间消息，使其获得完整消息操作并可随群聊一起清理。
        self._planner_final_writer = PlannerFinalReplyWriter(store=store, messages=self.messages)
        bridge.events.subscribe(self._planner_final_writer.handle_event)

    def create_room(self, **kwargs) -> dict[str, Any]:
        return self.rooms.create_room(**kwargs)

    def list_rooms(self) -> list[dict[str, Any]]:
        return self.rooms.list_rooms()

    def get_room(self, room_id: str) -> dict[str, Any]:
        return self.rooms.get_room(room_id)

    def update_room(self, room_id: str, **kwargs) -> dict[str, Any]:
        return self.rooms.update_room(room_id, **kwargs)

    def delete_room(self, room_id: str) -> dict[str, Any]:
        return self.rooms.delete_room(room_id)

    def list_messages(self, room_id: str) -> list[dict[str, Any]]:
        return self.messages.list_messages(room_id)

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self.messages.get_message(message_id)

    def add_message(self, **kwargs) -> dict[str, Any]:
        return self.messages.add_message(**kwargs)

    def list_agent_messages(self, agent_id: str, user_id: str = "") -> list[dict[str, Any]]:
        return self.messages.list_agent_messages(agent_id, user_id=user_id)

    def list_room_tasks(self, room_id: str) -> list[dict[str, Any]]:
        return self.runs.list_room_tasks(room_id)

    def list_room_run_ids(self, room_id: str) -> list[str]:
        return self.runs.list_room_run_ids(room_id)

    async def dispatch_message(self, **kwargs) -> dict[str, Any]:
        return await self.runs.dispatch_message(**kwargs)

    def cancel_room_run(self, **kwargs) -> dict[str, Any]:
        return self.runs.cancel_room_run(**kwargs)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.conversations.get_conversation(conversation_id)

    def list_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self.conversations.list_conversation_messages(conversation_id)

    def list_agent_conversations(self, agent_id: str, user_id: str = "") -> list[dict[str, Any]]:
        return self.conversations.list_agent_conversations(agent_id, user_id=user_id)

    def create_agent_conversation(self, **kwargs) -> dict[str, Any]:
        return self.conversations.create_agent_conversation(**kwargs)

    def delete_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.conversations.delete_conversation(conversation_id)

    def update_conversation(self, conversation_id: str, **kwargs) -> dict[str, Any]:
        return self.conversations.update_conversation(conversation_id, **kwargs)

    async def regenerate_conversation_reply(self, **kwargs) -> dict[str, Any]:
        return await self.conversations.regenerate_reply(**kwargs)

    # ── favorites / pinned context ────────────────────────────────
    def list_favorites(self, *, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        return self.favorites.list_favorites(scope_type=scope_type, scope_id=scope_id)

    def create_favorite(self, **kwargs) -> dict[str, Any]:
        return self.favorites.create_favorite(**kwargs)

    def favorite_message(self, **kwargs) -> dict[str, Any]:
        return self.favorites.favorite_message(**kwargs)

    def update_favorite(self, favorite_id: str, **kwargs) -> dict[str, Any]:
        return self.favorites.update_favorite(favorite_id, **kwargs)

    def delete_favorite(self, favorite_id: str) -> dict[str, Any]:
        return self.favorites.delete_favorite(favorite_id)

    def list_tools(self) -> list[dict[str, Any]]:
        return self.agents.list_tools()

    def add_conversation_message(self, **kwargs) -> dict[str, Any]:
        return self.conversations.add_conversation_message(**kwargs)

    async def reply_to_conversation_message(self, **kwargs) -> dict[str, Any]:
        return await self.conversations.reply_to_conversation_message(**kwargs)

    async def cancel_conversation_reply(self, **kwargs) -> dict[str, Any]:
        return await self.conversations.cancel_conversation_reply(**kwargs)

    async def reply_to_dm_message(self, *, room_id: str, message_id: str, auto_start: bool = True) -> dict[str, Any]:
        raise ValueError("单聊不再使用 room，请使用 /api/im/conversations/{conversation_id}/reply")

    def list_agents(self, user_id: str = "") -> list[dict[str, Any]]:
        return self.agents.list_visible_agents(user_id) if user_id else self.agents.list_agents()

    def list_contexts(self, user_id: str = "") -> list[dict[str, Any]]:
        return self.agents.list_visible_contexts(user_id) if user_id else self.agents.list_contexts()

    def create_agent(self, **kwargs) -> dict[str, Any]:
        return self.agents.create_agent(**kwargs)

    def delete_agent(self, agent_id: str, *, user_id: str = "") -> dict[str, Any]:
        return self.agents.delete_agent(agent_id, user_id=user_id)

    def record_action(self, **kwargs) -> dict[str, Any]:
        return self.actions.record_action(**kwargs)
