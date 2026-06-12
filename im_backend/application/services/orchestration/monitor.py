from __future__ import annotations

from typing import Any

from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge

# 仍在占用执行资源、可被中断的状态。
ACTIVE_STATUSES = {"pending", "running"}


class RunMonitorService:
    """跨单聊/群聊的「正在运行的智能体」全局视图 + 通用中断入口。

    两类运行来源（执行模型不同，统一成一种条目形态）：
    - orchestration：agent_flow plan/react run（群聊编排任务），记录在 runs 集合，
      asyncio task 由 RunOrchestrationService 持有，run_id 即取消句柄；
    - dm_reply：单聊回复任务，无 run 记录，由 ConversationService._reply_tasks 持有，
      取消句柄是触发回复的 user message_id。
    """

    def __init__(self, *, store, bridge: AgentFlowBridge, conversations, group_runs) -> None:
        self._store = store
        self._bridge = bridge
        self._conversations = conversations
        self._group_runs = group_runs

    def list_active_runs(self, recent_limit: int = 20) -> dict[str, Any]:
        active: list[dict[str, Any]] = []
        recent: list[dict[str, Any]] = []
        for record in self._bridge.runs.list_runs():
            item = self._trim_orchestration_run(record)
            if record.get("status") in ACTIVE_STATUSES:
                active.append(item)
            elif len(recent) < recent_limit:
                recent.append(item)
        # 单聊回复任务放在最前：它们通常是用户当下最关心的。
        active = self._conversations.list_active_replies() + active
        return {"items": active, "recent": recent}

    async def cancel(self, target_id: str) -> dict[str, Any]:
        """通用中断：自动识别目标是编排 run 还是单聊回复，复用既有取消逻辑与事件广播。"""
        run = self._bridge.runs.get_run(target_id)
        if run is not None:
            message = self._store.find_one("im_messages", {"run_id": target_id}) or {}
            room_id = message.get("room_id", "")
            if room_id:
                return self._group_runs.cancel_room_run(room_id=room_id, run_id=target_id)
            # 没有 IM 消息挂载（例如 API 直接创建的 run）：直接走 bridge 取消。
            cancelled = self._bridge.cancel_run(target_id)
            return {"type": "run_cancelled", "run_id": target_id, "cancelled": True, "run": cancelled}

        message = self._store.find_one("im_messages", {"message_id": target_id})
        if message and message.get("conversation_id") and message.get("sender_type") == "user":
            return await self._conversations.cancel_conversation_reply(
                conversation_id=message["conversation_id"],
                message_id=target_id,
            )
        raise KeyError(f"运行不存在或已结束: {target_id}")

    def _trim_orchestration_run(self, record: dict[str, Any]) -> dict[str, Any]:
        """裁剪 run 记录（plan/final 可能很大），并反查 IM 侧挂载关系。"""
        run_id = record.get("run_id", "")
        message = self._store.find_one("im_messages", {"run_id": run_id}) or {}
        room_id = message.get("room_id", "")
        room = self._store.find_one("im_rooms", {"room_id": room_id}) if room_id else None
        agent_ids = record.get("executor_agent_ids") or []
        if not agent_ids and record.get("executor_agent_id"):
            agent_ids = [record["executor_agent_id"]]
        return {
            "kind": "orchestration",
            "run_id": run_id,
            "status": record.get("status", ""),
            "mode": record.get("mode", ""),
            "prompt": str(record.get("prompt", ""))[:200],
            "agent_ids": agent_ids,
            "planner_agent_id": record.get("planner_agent_id", ""),
            "room_id": room_id,
            "room_title": (room or {}).get("title", ""),
            "conversation_id": message.get("conversation_id", ""),
            "conversation_title": "",
            "message_id": message.get("message_id", ""),
            "created_at": record.get("created_at"),
            "started_at": record.get("started_at"),
            "finished_at": record.get("finished_at"),
        }
