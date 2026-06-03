from __future__ import annotations

from fastapi import APIRouter

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from infra.deploy.manager import deployment_manager  # noqa: PLC0415

router = APIRouter()

@router.get("/deployments")
async def list_deployments():
    return {"items": deployment_manager.list()}


@router.delete("/deployments/{deployment_id}")
async def stop_deployment(deployment_id: str):
    stopped = await deployment_manager.stop(deployment_id)
    return {"stopped": stopped, "deployment_id": deployment_id}


@router.post("/deployments/{deployment_id}/touch")
async def touch_deployment(deployment_id: str):
    ok = deployment_manager.touch(deployment_id)
    return {"ok": ok}
