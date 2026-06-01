from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from im_backend.api.core import get_current_user, get_im_service
from im_backend.api.schemas import FavoriteCreateRequest, FavoriteUpdateRequest
from im_backend.application.services.facade import IMService


router = APIRouter()


@router.get("/favorites")
async def list_favorites(
    scope_type: str,
    scope_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    return {"items": service.list_favorites(scope_type=scope_type, scope_id=scope_id)}


@router.post("/favorites")
async def create_favorite(
    request: FavoriteCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.create_favorite(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            content=request.content,
            title=request.title,
            source_message_id=request.source_message_id,
            created_by=current_user["user_id"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.patch("/favorites/{favorite_id}")
async def update_favorite(
    favorite_id: str,
    request: FavoriteUpdateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        item = service.update_favorite(
            favorite_id,
            title=request.title,
            content=request.content,
            enabled=request.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.delete("/favorites/{favorite_id}")
async def delete_favorite(
    favorite_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        return {"item": service.delete_favorite(favorite_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
