from __future__ import annotations

from fastapi import APIRouter, Depends

from im_backend.api.core import get_current_user, get_im_service
from im_backend.application.services.facade import IMService


router = APIRouter()


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
