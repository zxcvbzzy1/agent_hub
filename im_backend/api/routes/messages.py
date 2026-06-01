from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from im_backend.api.core import get_current_user, get_im_service
from im_backend.api.schemas import MessageActionRequest, MessageFavoriteRequest
from im_backend.application.services.facade import IMService


router = APIRouter()


@router.post("/messages/{message_id}/actions")
async def record_action(
    message_id: str,
    request: MessageActionRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.record_action(
            message_id=message_id,
            action_type=request.action_type,
            actor_id=current_user["user_id"],
            payload=request.payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": item}


@router.post("/messages/{message_id}/favorite")
async def favorite_message(
    message_id: str,
    request: MessageFavoriteRequest = MessageFavoriteRequest(),
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.favorite_message(
            message_id=message_id,
            title=request.title,
            created_by=current_user["user_id"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}
