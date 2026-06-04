from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from im_backend.api.core import get_current_user
from im_backend.application.services.platform.skills import SkillFileService


router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_skill_service() -> SkillFileService:
    # Stateless over files — no shared state, safe to construct per request.
    return SkillFileService()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SkillCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    tags: Optional[list[str]] = []
    content: str
    id: Optional[str] = None  # caller-supplied skill_id; derived from name if absent


class SkillUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    tags: Optional[list[str]] = []
    content: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/skills")
async def list_skills(
    current_user: dict = Depends(get_current_user),
    service: SkillFileService = Depends(get_skill_service),
):
    _ = current_user
    return {"items": service.list_skills()}


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    service: SkillFileService = Depends(get_skill_service),
):
    _ = current_user
    try:
        return {"item": service.get_skill(skill_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/skills")
async def create_skill(
    request: SkillCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: SkillFileService = Depends(get_skill_service),
):
    _ = current_user
    try:
        item = service.create_skill(
            name=request.name,
            description=request.description or "",
            tags=request.tags or [],
            content=request.content,
            skill_id=request.id,
        )
    except ValueError as exc:
        if "exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.put("/skills/{skill_id}")
async def update_skill(
    skill_id: str,
    request: SkillUpdateRequest,
    current_user: dict = Depends(get_current_user),
    service: SkillFileService = Depends(get_skill_service),
):
    _ = current_user
    try:
        item = service.update_skill(
            skill_id=skill_id,
            name=request.name,
            description=request.description or "",
            tags=request.tags or [],
            content=request.content,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    service: SkillFileService = Depends(get_skill_service),
):
    _ = current_user
    try:
        service.delete_skill(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "id": skill_id}
