from __future__ import annotations

import asyncio
import json
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from im_backend.api.core import get_current_user, get_im_service

router = APIRouter()


@router.get("/rooms/{room_id}/workspace")
async def workspace(room_id: str, user=Depends(get_current_user), service=Depends(get_im_service)):
    try:
        return {"item": service.workspaces.detail(room_id, user["user_id"])}
    except KeyError as exc:
        raise HTTPException(404, "群聊不存在") from exc


@router.post("/rooms/{room_id}/workspace/import")
async def import_workspace(room_id: str, request: Request, user=Depends(get_current_user), service=Depends(get_im_service)):
    workspaces = service.workspaces
    try:
        workspaces.access(room_id, user["user_id"])
        received = 0
        # Bound the raw request as well as the extracted files, so multipart
        # spooling cannot consume unbounded disk before per-file validation.
        body_limit = workspaces.total_limit + 2 * 1024 * 1024 + workspaces.count_limit * 2048
        async def receive():
            nonlocal received
            message = await request.receive()
            received += len(message.get("body", b""))
            if received > body_limit:
                raise MultiPartException("目录导入请求超过总大小限制")
            return message
        bounded_request = Request(request.scope, receive=receive)
        async with bounded_request.form(max_files=workspaces.count_limit, max_fields=1) as form:
            manifest_text = form.get("manifest", "{}")
            if not isinstance(manifest_text, str) or len(manifest_text) > 2 * 1024 * 1024:
                raise ValueError("目录清单过大或格式错误")
            manifest = json.loads(manifest_text)
            paths, directories = manifest.get("paths", []), manifest.get("directories", [])
            if not isinstance(paths, list) or not isinstance(directories, list):
                raise ValueError("目录清单格式错误")
            uploads = form.getlist("files")
            if not all(isinstance(f, UploadFile) for f in uploads):
                raise ValueError("文件清单格式错误")
            copying = asyncio.create_task(run_in_threadpool(workspaces.prepare_import,
                room_id, user["user_id"], paths, directories, uploads))
            try:
                path = await asyncio.shield(copying)
            except asyncio.CancelledError:
                # A thread cannot be canceled halfway through copying. Wait for
                # its result and remove the copy without activating the workspace.
                path = await copying
                await run_in_threadpool(shutil.rmtree, path, True)
                raise
            try:
                if await request.is_disconnected():
                    raise ValueError("目录导入已取消")
                room = await workspaces.activate(room_id, user["user_id"], path)
            except BaseException:
                # Do not remove an activated directory if only event publishing failed.
                current = service.rooms.get_room(room_id)
                if (current.get("metadata") or {}).get("workdir") != path:
                    await run_in_threadpool(shutil.rmtree, path, True)
                raise
        return {"item": room, "workdir": path}
    except KeyError as exc:
        raise HTTPException(404, "群聊不存在") from exc
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        raise HTTPException(400, str(exc)) from exc
