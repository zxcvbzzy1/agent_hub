from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from im_backend.api.core import get_agent_catalog, get_current_user, get_im_service
from im_backend.api.schemas import AgentConversationCreateRequest
from im_backend.application.services import AgentCatalogService, IMService


router = APIRouter()


@router.get("/agents")
async def list_agents(service: AgentCatalogService = Depends(get_agent_catalog)):
    return {"items": service.list_agents()}


@router.get("/agents/{agent_id}/messages")
async def list_agent_messages(agent_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"items": service.list_agent_messages(agent_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/conversations")
async def list_agent_conversations(agent_id: str, service: IMService = Depends(get_im_service)):
    try:
        return {"items": service.list_agent_conversations(agent_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/conversations")
async def create_agent_conversation(
    agent_id: str,
    request: AgentConversationCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.create_agent_conversation(
            agent_id=agent_id,
            created_by=current_user["user_id"],
            title=request.title,
            avatar_url=request.avatar_url,
            metadata={**request.metadata, "created_by_username": current_user["username"]},
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}
