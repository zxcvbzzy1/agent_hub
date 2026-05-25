from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from im_backend.api.core import (
    get_agent_catalog,
    get_artifact_storage,
    get_im_service,
    get_room_events,
)
from im_backend.api.schemas import (
    ArtifactUploadRequest,
    DispatchRequest,
    MessageActionRequest,
    MessageCreateRequest,
    RoomCreateRequest,
)
from im_backend.application.event_stream import RoomEventStreamService
from im_backend.application.services import AgentCatalogService, IMService
from im_backend.infra.storage.artifacts import ArtifactStorage


router = APIRouter(prefix="/api/im", tags=["im"])


@router.get("/agents")
async def list_agents(service: AgentCatalogService = Depends(get_agent_catalog)):
    return {"items": service.list_agents()}


@router.post("/rooms")
async def create_room(request: RoomCreateRequest, service: IMService = Depends(get_im_service)):
    try:
        item = service.create_room(
            type=request.type,
            title=request.title,
            member_agent_ids=request.member_agent_ids,
            created_by=request.created_by,
            avatar_url=request.avatar_url,
            metadata=request.metadata,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.get("/rooms")
async def list_rooms(service: IMService = Depends(get_im_service)):
    return {"items": service.list_rooms()}


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"item": service.get_room(room_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/rooms/{room_id}/messages")
async def list_messages(room_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"items": service.list_messages(room_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/rooms/{room_id}/messages")
async def add_message(
    room_id: str,
    request: MessageCreateRequest,
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.add_message(
            room_id=room_id,
            sender_type=request.sender_type,
            sender_id=request.sender_id,
            content_parts=[part.model_dump() for part in request.content_parts],
            mentions=request.mentions,
            reply_to=request.reply_to,
            quote_of=request.quote_of,
            run_id=request.run_id,
            status=request.status,
            metadata=request.metadata,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.post("/rooms/{room_id}/dispatch")
async def dispatch_message(
    room_id: str,
    request: DispatchRequest,
    service: IMService = Depends(get_im_service),
):
    try:
        item = await service.dispatch_message(
            room_id=room_id,
            message_id=request.message_id,
            planner_agent_id=request.planner_agent_id,
            context_id=request.context_id,
            max_replan_rounds=request.max_replan_rounds,
            auto_start=request.auto_start,
            approved=request.approved,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.get("/rooms/{room_id}/stream")
async def stream_room(
    room_id: str,
    service: IMService = Depends(get_im_service),
    events: RoomEventStreamService = Depends(get_room_events),
):
    try:
        service.get_room(room_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        events.stream(room_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/messages/{message_id}/actions")
async def record_action(
    message_id: str,
    request: MessageActionRequest,
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.record_action(
            message_id=message_id,
            action_type=request.action_type,
            actor_id=request.actor_id,
            payload=request.payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": item}


@router.post("/artifacts/upload")
async def upload_artifact(
    request: ArtifactUploadRequest,
    storage: ArtifactStorage = Depends(get_artifact_storage),
):
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
