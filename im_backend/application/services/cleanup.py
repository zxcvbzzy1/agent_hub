from __future__ import annotations

import json
from typing import Any


class IMCleanupService:
    """Centralized hard-delete helpers for IM-owned records."""

    def __init__(self, store) -> None:
        self._store = store

    def delete_conversation(self, conversation_id: str) -> dict[str, int]:
        messages = self._store.find_many("im_messages", {"conversation_id": conversation_id})
        run_ids = self._run_ids(messages)
        stats = {
            "conversations": self._store.delete_one("im_conversations", {"conversation_id": conversation_id}),
            "messages": self._store.delete_many("im_messages", {"conversation_id": conversation_id}),
            "im_events": self._delete_scope_events(conversation_id),
            "runtime_events": self._store.delete_many("events", {"run_id": conversation_id}),
            "runs": 0,
            "message_actions": self._delete_message_actions(messages),
        }
        stats["runtime_events"] += self._delete_runtime_for_runs(run_ids)
        stats["runs"] += self._delete_runs(run_ids)
        return stats

    def delete_room(self, room_id: str) -> dict[str, int]:
        messages = self._store.find_many("im_messages", {"room_id": room_id})
        run_ids = self._run_ids(messages)
        stats = {
            "rooms": self._store.delete_one("im_rooms", {"room_id": room_id}),
            "messages": self._store.delete_many("im_messages", {"room_id": room_id}),
            "im_events": self._delete_scope_events(room_id),
            "runtime_events": self._delete_runtime_for_runs(run_ids),
            "runs": self._delete_runs(run_ids),
            "message_actions": self._delete_message_actions(messages),
        }
        return stats

    def delete_agent_im_refs(self, agent_id: str) -> dict[str, int]:
        stats = {
            "conversations": 0,
            "messages": 0,
            "im_events": 0,
            "runtime_events": 0,
            "runs": 0,
            "message_actions": 0,
            "rooms_updated": 0,
        }
        for conversation in self._store.find_many("im_conversations", {"agent_id": agent_id}):
            self._add_stats(stats, self.delete_conversation(conversation["conversation_id"]))

        for room in self._store.find_many("im_rooms", {"type": "group"}):
            members = room.get("member_agent_ids") or []
            metadata = dict(room.get("metadata") or {})
            changed = False
            if agent_id in members:
                members = [member for member in members if member != agent_id]
                changed = True
            if metadata.get("planner_agent_id") == agent_id:
                metadata["planner_agent_id"] = "default_planner"
                changed = True
            if changed:
                self._store.update_one(
                    "im_rooms",
                    {"room_id": room["room_id"]},
                    {"member_agent_ids": members, "metadata": metadata},
                )
                stats["rooms_updated"] += 1

            for message in self._agent_related_messages(room["room_id"], agent_id):
                self._add_stats(stats, self.delete_message(message))

        stats["im_events"] += self._delete_agent_events(agent_id)
        return stats

    def delete_message(self, message: dict[str, Any]) -> dict[str, int]:
        message_id = message.get("message_id", "")
        run_id = message.get("run_id", "")
        stats = {
            "messages": self._store.delete_one("im_messages", {"message_id": message_id}),
            "message_actions": self._store.delete_many("im_message_actions", {"message_id": message_id}),
            "im_events": 0,
            "runtime_events": 0,
            "runs": 0,
        }
        if run_id:
            stats["runtime_events"] += self._delete_runtime_for_runs([run_id])
            stats["runs"] += self._delete_runs([run_id])
        return stats

    def _agent_related_messages(self, room_id: str, agent_id: str) -> list[dict[str, Any]]:
        return [
            message
            for message in self._store.find_many("im_messages", {"room_id": room_id})
            if message.get("sender_id") == agent_id or agent_id in (message.get("mentions") or [])
        ]

    def _delete_scope_events(self, scope_id: str) -> int:
        return self._store.delete_many("im_events", {"scope_id": scope_id}) + self._store.delete_many(
            "im_events", {"room_id": scope_id}
        )

    def _delete_agent_events(self, agent_id: str) -> int:
        deleted = 0
        for event in self._store.find_many("im_events"):
            if self._event_mentions_agent(event, agent_id):
                deleted += self._store.delete_one("im_events", {"event_id": event.get("event_id", "")})
        return deleted

    def _event_mentions_agent(self, event: dict[str, Any], agent_id: str) -> bool:
        try:
            return agent_id in json.dumps(event, ensure_ascii=False)
        except TypeError:
            return False

    def _delete_runtime_for_runs(self, run_ids: list[str]) -> int:
        return sum(self._store.delete_many("events", {"run_id": run_id}) for run_id in run_ids)

    def _delete_runs(self, run_ids: list[str]) -> int:
        return sum(self._store.delete_one("runs", {"run_id": run_id}) for run_id in run_ids)

    def _delete_message_actions(self, messages: list[dict[str, Any]]) -> int:
        return sum(
            self._store.delete_many("im_message_actions", {"message_id": message.get("message_id", "")})
            for message in messages
        )

    def _run_ids(self, messages: list[dict[str, Any]]) -> list[str]:
        return [message["run_id"] for message in messages if message.get("run_id")]

    def _add_stats(self, target: dict[str, int], source: dict[str, int]) -> None:
        for key, value in source.items():
            target[key] = target.get(key, 0) + value
