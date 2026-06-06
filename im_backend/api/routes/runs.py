from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from im_backend.api.core import get_current_user, get_im_service
from im_backend.application.services.facade import IMService


router = APIRouter()


class ConfirmationResolveRequest(BaseModel):
    approved: bool
    reason: str = ""


@router.get("/runs/{run_id}/confirmations")
async def list_run_confirmations(
    run_id: str,
    service: IMService = Depends(get_im_service),
    current_user: dict = Depends(get_current_user),
):
    """列出该 run 待处理的人工确认（前端重连后可补拉，避免错过 SSE）。"""
    _ = current_user
    return {"items": service._bridge.human_confirmations.list_pending(run_id)}


@router.post("/runs/{run_id}/confirmations/{confirmation_id}")
async def resolve_run_confirmation(
    run_id: str,
    confirmation_id: str,
    request: ConfirmationResolveRequest,
    service: IMService = Depends(get_im_service),
    current_user: dict = Depends(get_current_user),
):
    """解析一条人工确认（允许/拒绝），唤醒在 agent_flow 侧等待的工具调用。"""
    _ = current_user
    try:
        return service._bridge.human_confirmations.resolve(
            run_id=run_id,
            confirmation_id=confirmation_id,
            approved=request.approved,
            reason=request.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="确认请求不存在或已处理") from exc


@router.get("/runs/{run_id}/events")
async def list_run_events(
    run_id: str,
    service: IMService = Depends(get_im_service),
    current_user: dict = Depends(get_current_user),
):
    """按 run_id 拉取该 run 的全量 runtime 事件（含被 SSE 历史回放剥离的重负载字段）。

    供前端 trace-card 懒加载：折叠态只显示数量，用户展开某条 trace 时才调用本接口
    取回完整事件正文，避免进入会话即全量加载导致卡顿。
    """
    events = service._bridge.events.list_events(run_id)
    return {"items": events}
