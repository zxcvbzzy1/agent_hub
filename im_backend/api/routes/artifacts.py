from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from im_backend.api.core import get_artifact_storage, get_current_user
from im_backend.api.schemas import ArtifactUploadRequest
from im_backend.infra.storage.artifacts import ArtifactStorage


router = APIRouter()


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
