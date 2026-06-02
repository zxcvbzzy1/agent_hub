from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from im_backend.api.core import get_agent_catalog, get_current_user, get_im_service
from im_backend.api.schemas import AgentConversationCreateRequest, AgentCreateRequest
from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.facade import IMService


router = APIRouter()


@router.get("/agents")
async def list_agents(
    current_user: dict = Depends(get_current_user),
    service: IMAgentService = Depends(get_agent_catalog),
):
    return {"items": service.list_visible_agents(current_user["user_id"])}


@router.get("/contexts")
async def list_contexts(
    current_user: dict = Depends(get_current_user),
    service: IMAgentService = Depends(get_agent_catalog),
):
    return {"items": service.list_visible_contexts(current_user["user_id"])}


@router.get("/tools")
async def list_tools(
    current_user: dict = Depends(get_current_user),
    service: IMAgentService = Depends(get_agent_catalog),
):
    _ = current_user
    return {"items": service.list_tools()}


@router.post("/agents")
async def create_agent(
    request: AgentCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        item = service.create_agent(
            name=request.name,
            agent_type=request.agent_type,
            context_id=request.context_id,
            role_prompt=request.role_prompt,
            metadata={**request.metadata, "created_by": current_user["user_id"], "created_by_username": current_user["username"]},
            owner_user_id=current_user["user_id"],
            tool_names=request.tool_names,
            tool_fields=request.tool_fields,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    _ = current_user
    try:
        return {"item": service.delete_agent(agent_id, user_id=current_user["user_id"])}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/messages")
async def list_agent_messages(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        return {"items": service.list_agent_messages(agent_id, user_id=current_user["user_id"])}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/conversations")
async def list_agent_conversations(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    service: IMService = Depends(get_im_service),
):
    try:
        return {"items": service.list_agent_conversations(agent_id, user_id=current_user["user_id"])}
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
