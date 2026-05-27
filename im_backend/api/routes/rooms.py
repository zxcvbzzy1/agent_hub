from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from im_backend.api.core import get_current_user, get_im_service, get_room_events
from im_backend.api.schemas import DispatchRequest, MessageCreateRequest, RoomCreateRequest
from im_backend.application.event_stream import RoomEventStreamService
from im_backend.application.services import IMService


router = APIRouter()


@router.post("/rooms")
async def create_room(
    request: RoomCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.create_room(
            type=request.type,
            title=request.title,
            member_agent_ids=request.member_agent_ids,
            created_by=current_user["user_id"],
            avatar_url=request.avatar_url,
            metadata={**request.metadata, "created_by_username": current_user["username"]},
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rooms/{room_id}/messages")
async def add_message(
    room_id: str,
    request: MessageCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        sender_type = request.sender_type
        sender_id = request.sender_id
        if sender_type == "user":
            sender_id = current_user["user_id"]
        item = service.add_message(
            room_id=room_id,
            sender_type=sender_type,
            sender_id=sender_id,
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


@router.get("/rooms/{room_id}/tasks")
async def list_room_tasks(room_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"items": service.list_room_tasks(room_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rooms/{room_id}/dispatch")
async def dispatch_message(
    room_id: str,
    request: DispatchRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
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
