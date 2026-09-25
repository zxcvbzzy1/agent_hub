from __future__ import annotations

import json
from typing import Any


class IMCleanupService:
    """Centralized hard-delete helpers for IM-owned records."""

    def __init__(self, store, runtime=None) -> None:
        self._store = store
        self.runtime = runtime

    async def delete_conversation(self, conversation_id: str) -> dict[str, int]:
        self._store.delete_many("im_conversation_files", {"conversation_id": conversation_id})
        messages = self._store.find_many("im_messages", {"conversation_id": conversation_id})
        run_ids = self._run_ids(messages)
        run_count = sum(self._store.find_one("runs", {"run_id": rid}) is not None for rid in run_ids)
        runtime_deleted = await self._delete_runtime_for_runs(run_ids)
        for message in messages:
            await self._remove_message_events(message)
        if self.runtime:
            for message in messages:
                if message.get("sender_type") == "user" and not message.get("run_id"):
                    await self.runtime.delete_runtime(message.get("conversation_id", ""),
                        kind="dm_reply", target_id=message["message_id"])
        stats = {
            "conversations": self._store.delete_one("im_conversations", {"conversation_id": conversation_id}),
            "messages": self._store.delete_many("im_messages", {"conversation_id": conversation_id}),
            "im_events": await self._delete_scope_events(conversation_id),
            "runtime_events": (await self.runtime.journal.delete("run", conversation_id)) if self.runtime else
                self._store.delete_many("events", {"run_id": conversation_id}),
            "runs": run_count,
            "message_actions": self._delete_message_actions(messages),
        }
        stats["runtime_events"] += runtime_deleted
        return stats

    async def delete_room(self, room_id: str) -> dict[str, int]:
        self._store.delete_many("im_conversation_files", {"room_id": room_id})
        messages = self._store.find_many("im_messages", {"room_id": room_id})
        run_ids = self._run_ids(messages)
        run_count = sum(self._store.find_one("runs", {"run_id": rid}) is not None for rid in run_ids)
        runtime_deleted = await self._delete_runtime_for_runs(run_ids)
        for message in messages:
            await self._remove_message_events(message)
        if self.runtime:
            for message in messages:
                if message.get("sender_type") == "user" and not message.get("run_id"):
                    await self.runtime.delete_runtime(message.get("conversation_id", ""),
                        kind="dm_reply", target_id=message["message_id"])
        stats = {
            "rooms": self._store.delete_one("im_rooms", {"room_id": room_id}),
            "messages": self._store.delete_many("im_messages", {"room_id": room_id}),
            "im_events": await self._delete_scope_events(room_id),
            "runtime_events": runtime_deleted,
            "runs": run_count,
            "message_actions": self._delete_message_actions(messages),
            # 群聊每次编排都会在 agent_flow 的 conversations/messages/runs 里建一份运行态镜像
            # （room_id 仅存在于 metadata 中），旧的 delete_room 只清 im_* 集合，会把这些运行态记录留成孤儿。
            "runtime_conversations": 0,
            "runtime_messages": 0,
            "runtime_runs": 0,
        }
        self._add_stats(stats, (await self._delete_runtime_scope_by_room(room_id)))
        return stats

    async def delete_agent_im_refs(self, agent_id: str) -> dict[str, int]:
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
            self._add_stats(stats, (await self.delete_conversation(conversation["conversation_id"])))

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
                self._add_stats(stats, (await self.delete_message(message)))

        stats["im_events"] += await self._delete_agent_events(agent_id)
        return stats

    async def delete_message(self, message: dict[str, Any]) -> dict[str, int]:
        ids = self._run_ids([message]) if message.get("sender_type") == "user" else []
        runtime_deleted = await self._delete_runtime_for_runs(ids)
        await self._remove_message_events(message)
        message_id = message.get("message_id", "")
        self._store.delete_many("im_conversation_files", {"message_id": message_id})
        return {
            "messages": self._store.delete_one("im_messages", {"message_id": message_id}),
            "message_actions": self._store.delete_many("im_message_actions", {"message_id": message_id}),
            "im_events": 0, "runtime_events": runtime_deleted, "runs": len(ids),
        }

    async def _remove_message_events(self, message):
        scope = message.get("room_id") or message.get("conversation_id")
        mid = message["message_id"]
        def matches(event):
            payload = event.get("payload") or {}
            return (payload.get("message_id") == mid or
                    (payload.get("message") or {}).get("message_id") == mid or
                    (payload.get("reply") or {}).get("message_id") == mid)
        if self.runtime and scope:
            await self.runtime.remove_projected(scope, matches)
        else:
            for event in self._store.find_many("im_events", {"scope_id": scope}):
                if matches(event):
                    self._store.delete_one("im_events", {"event_id": event["event_id"]})

    def _agent_related_messages(self, room_id: str, agent_id: str) -> list[dict[str, Any]]:
        return [
            message
            for message in self._store.find_many("im_messages", {"room_id": room_id})
            if message.get("sender_id") == agent_id or agent_id in (message.get("mentions") or [])
        ]

    async def _delete_scope_events(self, scope_id: str) -> int:
        if self.runtime:
            count = await self.runtime.journal.delete('scope', scope_id)
            # Legacy records can lack scope_id/version and are not in v3 snapshots.
            return count + self._store.delete_many('im_events', {'room_id': scope_id})
        return self._store.delete_many('im_events', {'scope_id': scope_id}) + self._store.delete_many(
            'im_events', {'room_id': scope_id})

    async def _delete_agent_events(self, agent_id: str) -> int:
        records = self._store.find_many('im_events')
        scopes = {e.get('scope_id') for e in records if e.get('scope_id')}
        if self.runtime:
            scopes.update(await self.runtime.redis.smembers(self.runtime.journal.key('scope:scopes')))
            count = 0
            for scope in scopes:
                count += await self.runtime.remove_projected(scope, lambda e: self._event_mentions_agent(e, agent_id))
            return count
        return sum(self._store.delete_one('im_events', {'event_id': e['event_id']})
                   for e in records if self._event_mentions_agent(e, agent_id))

    def _event_mentions_agent(self, event: dict[str, Any], agent_id: str) -> bool:
        try:
            return agent_id in json.dumps(event, ensure_ascii=False)
        except TypeError:
            return False

    async def _delete_runtime_scope_by_room(self, room_id: str) -> dict[str, int]:
        """删除 agent_flow 运行态镜像：room 关联的 conversations / messages / runs / events。

        in-memory fallback store 的查询不支持 ``metadata.room_id`` 点号路径，这里全量扫描
        conversations 后在 Python 侧按 ``metadata.room_id`` 过滤，与本类其它清理逻辑一致。
        """
        stats = {"runtime_conversations": 0, "runtime_messages": 0, "runtime_runs": 0, "runtime_events": 0}
        for conversation in self._store.find_many("conversations", {}):
            if (conversation.get("metadata") or {}).get("room_id") != room_id:
                continue
            conversation_id = conversation.get("conversation_id", "")
            if not conversation_id:
                continue
            runtime_messages = self._store.find_many("messages", {"conversation_id": conversation_id})
            runtime_runs = self._store.find_many("runs", {"conversation_id": conversation_id})
            run_ids = [
                run_id
                for run_id in (
                    [run.get("run_id") for run in runtime_runs]
                    + [message.get("run_id") for message in runtime_messages]
                )
                if run_id
            ]
            run_ids = list(dict.fromkeys(run_ids))
            stats["runtime_events"] += await self._delete_runtime_for_runs(run_ids)
            stats["runtime_runs"] += len(runtime_runs)
            stats["runtime_runs"] += self._store.delete_many("runs", {"conversation_id": conversation_id})
            stats["runtime_messages"] += self._store.delete_many("messages", {"conversation_id": conversation_id})
            stats["runtime_conversations"] += self._store.delete_one(
                "conversations", {"conversation_id": conversation_id}
            )
        return stats

    async def _delete_runtime_for_runs(self, run_ids: list[str]) -> int:
        from application.services.run_state import RunStateService
        count = 0
        for run_id in set(run_ids):
            if self.runtime:
                result = await RunStateService(self._store, self.runtime).delete(run_id)
                count += result["events"]
            else:
                count += self._store.delete_many("events", {"run_id": run_id})
                self._store.delete_many("im_events", {"run_id": run_id})
                self._store.delete_one("runs", {"run_id": run_id})
        return count

    def _delete_message_actions(self, messages: list[dict[str, Any]]) -> int:
        return sum(
            self._store.delete_many("im_message_actions", {"message_id": message.get("message_id", "")})
            for message in messages
        )

    def _run_ids(self, messages: list[dict[str, Any]]) -> list[str]:
        ids = {m["run_id"] for m in messages if m.get("run_id")}
        for message in messages:
            if message.get("sender_type") == "user":
                ids.update(r["run_id"] for r in self._store.find_many(
                    "runs", {"source_message_id": message["message_id"]}))
        return list(ids)

    def _add_stats(self, target: dict[str, int], source: dict[str, int]) -> None:
        for key, value in source.items():
            target[key] = target.get(key, 0) + value
