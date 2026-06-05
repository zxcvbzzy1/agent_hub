from __future__ import annotations

import base64
import io
import urllib.parse
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from im_backend.api.core import get_artifact_storage, get_current_user
from im_backend.api.schemas import ArtifactBundleRequest, ArtifactUploadRequest
from im_backend.application.services._shared.deploy_files import resolve_deploy_workdir
from im_backend.application.services._shared.inline_artifacts import (
    _safe_filename,
    artifact_download_file,
)
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
from im_backend.infra.storage.artifacts import ArtifactStorage

ensure_agent_flow_path()
from infra.tool.builtin import diff_editor  # type: ignore  # noqa: E402


router = APIRouter()


class SaveDocumentRequest(BaseModel):
    agent_id: str
    file_path: str
    content: str
    base_sha: str | None = None


class RevertRequest(BaseModel):
    agent_id: str
    file_path: str
    version: int


_STATUS_TO_HTTP = {"conflict": 409, "expired": 410, "error": 400}


def _raise_for_status(result: dict) -> dict:
    status = result.get("status")
    if status and status != "applied":
        code = _STATUS_TO_HTTP.get(status, 400)
        # detail 用干净的文案（前端全局拦截器会直接 toast），状态码用于前端区分冲突/过期
        raise HTTPException(status_code=code, detail=result.get("message") or status)
    return result


@router.post("/artifacts/edits/{edit_id}/apply")
async def apply_edit(edit_id: str, current_user: dict = Depends(get_current_user)):
    """一键应用某条 diff_editor 生成的 Diff（内容/路径取自服务端 pending，前端只传 edit_id）。"""
    _ = current_user
    result = diff_editor.apply_pending_edit(edit_id)
    return _raise_for_status(result)


@router.post("/artifacts/files/save")
async def save_artifact_file(
    request: SaveDocumentRequest, current_user: dict = Depends(get_current_user)
):
    """文档卡片编辑回写原文件（限定 agent 工作目录内）。"""
    _ = current_user
    result = diff_editor.save_document(
        request.agent_id, request.file_path, request.content, request.base_sha
    )
    return _raise_for_status(result)


@router.get("/artifacts/edits/history")
async def edit_history(
    agent_id: str, file_path: str, current_user: dict = Depends(get_current_user)
):
    """某文件的版本历史（工作区快照）。"""
    _ = current_user
    return diff_editor.list_history(agent_id, file_path)


@router.post("/artifacts/edits/revert")
async def revert_edit(request: RevertRequest, current_user: dict = Depends(get_current_user)):
    """把某文件回退到指定版本。"""
    _ = current_user
    result = diff_editor.revert_version(request.agent_id, request.file_path, request.version)
    return _raise_for_status(result)


def _bundle_deploy_dir(zf: zipfile.ZipFile, art: dict, index: int, used_names: set[str]) -> bool:
    """把 deploy 产物的部署目录文件平铺进 bundle 的 <title>/ 子目录（复用新的压缩包路径）。

    成功写入返回 True；无法解析部署目录（如越界 / 已回收 / 空目录）返回 False，
    由调用方退回默认的文本处理。
    """
    workdir = resolve_deploy_workdir(art.get("deployment_id"), art.get("download_dir"))
    if workdir is None:
        return False
    folder = _safe_filename(str(art.get("title") or ""), f"deploy-{index}")
    if folder in used_names:
        folder = f"{index}_{folder}"
    wrote = False
    for path in workdir.rglob("*"):
        if path.is_file():
            zf.writestr(f"{folder}/{path.relative_to(workdir)}", path.read_bytes())
            wrote = True
    if wrote:
        used_names.add(folder)
    return wrote


@router.get("/artifacts")
async def list_artifacts(storage: ArtifactStorage = Depends(get_artifact_storage)):
    return {"items": storage.list()}


@router.post("/artifacts/upload")
async def upload_artifact(
    request: ArtifactUploadRequest,
    current_user: dict = Depends(get_current_user),
    storage: ArtifactStorage = Depends(get_artifact_storage),
):
    _ = current_user
    try:
        content = base64.b64decode(request.content_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="content_base64 无法解码") from exc
    item = storage.save_bytes(
        content=content,
        filename=request.filename,
        content_type=request.content_type,
    )
    return {"item": item}


@router.post("/artifacts/bundle")
async def bundle_artifacts(
    request: ArtifactBundleRequest,
    current_user: dict = Depends(get_current_user),
    storage: ArtifactStorage = Depends(get_artifact_storage),
):
    _ = current_user
    if not request.artifacts:
        raise HTTPException(status_code=400, detail="没有可打包的产物")

    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, art in enumerate(request.artifacts):
            # deploy 产物走新的压缩包路径：把部署目录文件平铺进 <title>/ 子目录
            if str(art.get("type", "")).strip().lower() == "deploy":
                if _bundle_deploy_dir(zf, art, index, used_names):
                    continue
            name, data = artifact_download_file(art, index=index, storage=storage)
            if name in used_names:
                name = f"{index}_{name}"
            used_names.add(name)
            zf.writestr(name, data)

    buf.seek(0)
    fname = request.filename or "artifacts.zip"
    encoded_fname = urllib.parse.quote(fname)
    content_disposition = f'attachment; filename="download.zip"; filename*=UTF-8\'\'{encoded_fname}'
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    storage: ArtifactStorage = Depends(get_artifact_storage),
):
    item = storage.get(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = Path(item["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file not found")
    return FileResponse(path, media_type=item.get("content_type") or None, filename=item.get("filename"))
