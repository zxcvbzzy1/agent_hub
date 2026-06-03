from __future__ import annotations

import base64
import io
import urllib.parse
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from im_backend.api.core import get_artifact_storage, get_current_user
from im_backend.api.schemas import ArtifactBundleRequest, ArtifactUploadRequest
from im_backend.application.services._shared.deploy_files import resolve_deploy_workdir
from im_backend.application.services._shared.inline_artifacts import (
    _safe_filename,
    artifact_download_file,
)
from im_backend.infra.storage.artifacts import ArtifactStorage


router = APIRouter()


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
