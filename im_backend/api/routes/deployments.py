from __future__ import annotations

import io
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from im_backend.application.services._shared.deploy_files import zip_dir_bytes
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from infra.deploy.manager import deployment_manager, DEPLOY_ROOT  # noqa: PLC0415

router = APIRouter()

@router.get("/deployments")
async def list_deployments():
    return {"items": deployment_manager.list()}


@router.get("/deployments/{deployment_id}/download")
async def download_deployment(deployment_id: str, dir: str | None = None):
    dep = deployment_manager.get(deployment_id)
    if dep is not None:
        # 部署仍在内存中：以其 workdir 为权威，忽略客户端传入路径
        workdir = Path(dep.workdir)
    elif dir:
        # 回退：客户端提供持久化的 download_dir，必须位于 DEPLOY_ROOT 内
        candidate = Path(dir).resolve()
        try:
            candidate.relative_to(DEPLOY_ROOT)
        except ValueError:
            raise HTTPException(status_code=403, detail="下载目录越界，已拒绝")
        workdir = candidate
    else:
        raise HTTPException(status_code=404, detail="部署不存在")

    if not workdir.is_dir():
        raise HTTPException(status_code=404, detail="部署目录不存在")

    data = zip_dir_bytes(workdir)
    fname = f"{deployment_id}.zip"
    encoded_fname = urllib.parse.quote(fname)
    content_disposition = (
        f'attachment; filename="download.zip"; filename*=UTF-8\'\'{encoded_fname}'
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/deployments/{deployment_id}/restart")
async def restart_deployment(deployment_id: str):
    dep = await deployment_manager.restart(deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="部署信息不存在或已丢失（后端可能已重启），请让 Agent 重新部署")
    return dep.to_public_dict()


@router.delete("/deployments/{deployment_id}")
async def stop_deployment(deployment_id: str):
    stopped = await deployment_manager.stop(deployment_id)
    return {"stopped": stopped, "deployment_id": deployment_id}


@router.post("/deployments/{deployment_id}/touch")
async def touch_deployment(deployment_id: str):
    ok = deployment_manager.touch(deployment_id)
    return {"ok": ok}
