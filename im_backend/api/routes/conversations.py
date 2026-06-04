from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from im_backend.api.core import get_current_user, get_im_service, get_room_events
from im_backend.api.schemas import (
    ConversationUpdateRequest,
    MessageCreateRequest,
    RegenerateRequest,
    ReplyRequest,
)
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.facade import IMService


router = APIRouter()


@router.get("/activity")
async def list_activity(
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    return {"items": service.list_activity(user_id=current_user["user_id"])}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"item": service.get_conversation(conversation_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/messages")
async def list_conversation_messages(conversation_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"items": service.list_conversation_messages(conversation_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/conversations/{conversation_id}/messages")
async def add_conversation_message(
    conversation_id: str,
    request: MessageCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        sender_type = request.sender_type
        sender_id = request.sender_id
        if sender_type == "user":
            sender_id = current_user["user_id"]
        item = service.add_conversation_message(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content_parts=[part.model_dump() for part in request.content_parts],
            reply_to=request.reply_to,
            quote_of=request.quote_of,
            status=request.status,
            metadata=request.metadata,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.post("/conversations/{conversation_id}/reply")
async def reply_to_conversation_message(
    conversation_id: str,
    request: ReplyRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        item = await service.reply_to_conversation_message(
            conversation_id=conversation_id,
            message_id=request.message_id,
            auto_start=request.auto_start,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.post("/conversations/{conversation_id}/messages/{message_id}/cancel")
async def cancel_conversation_message(
    conversation_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        item = await service.cancel_conversation_reply(
            conversation_id=conversation_id,
            message_id=message_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        item = service.update_conversation(
            conversation_id,
            pinned=request.pinned,
            archived=request.archived,
            title=request.title,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_conversation_message(
    conversation_id: str,
    message_id: str,
    request: RegenerateRequest = RegenerateRequest(),
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        item = await service.regenerate_conversation_reply(
            conversation_id=conversation_id,
            message_id=message_id,
            auto_start=request.auto_start,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        return {"item": service.delete_conversation(conversation_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/events")
async def stream_conversation_events(
    conversation_id: str,
    service: IMService = Depends(get_im_service),
    events: RoomEventStreamService = Depends(get_room_events),
):
    try:
        service.get_conversation(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        events.stream_merged(
            conversation_id,
            runtime_events=service._bridge.events,
            runtime_ids_provider=lambda: [conversation_id],
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
