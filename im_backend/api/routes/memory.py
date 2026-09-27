import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from im_backend.api.core import get_current_user, get_container
from im_backend.application.services.platform.memory import MemoryManagementService
from im_backend.domain.memory_settings import RetrievalSettings

router = APIRouter(prefix="/memory", tags=["memory"])


def get_memory_service():
    container = get_container()
    return MemoryManagementService(container.bridge.long_memory, container.store,
                                   container.bridge.memory_management_repository)


class RetrievalSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    limit: int = Field(default=6, ge=1, le=50, strict=True)
    token_budget: int = Field(default=4000, ge=128, le=32000, strict=True)
    k1: float = Field(default=1.5, gt=0, le=5)
    b: float = Field(default=0.75, ge=0, le=1)

    def to_config(self):
        return RetrievalSettings(**self.model_dump())


class RecallTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=20000)
    config: RetrievalSettingsRequest | None = None


async def invoke(method, *args, **kwargs):
    try:
        return await asyncio.to_thread(method, *args, **kwargs)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="记忆或来源文件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="记忆文件暂时无法读取，请重试") from exc


@router.get("/blocks")
async def list_blocks(q: str = Query(default="", max_length=1000),
    status: Literal["active", "all", "deleted", "expired", "merged", "superseded", "unavailable"] = "active",
    room_id: str | None = None, conversation_id: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.list_blocks, user["user_id"], q=q, status=status, room_id=room_id,
                        conversation_id=conversation_id, page=page, page_size=page_size)


@router.get("/blocks/{block_id}")
async def block_detail(block_id: str, user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.block_detail, user["user_id"], block_id)


@router.get("/sources/{source_id}")
async def source_detail(source_id: str, user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.source_detail, user["user_id"], source_id)


@router.get("/scopes")
async def scopes(user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.scopes, user["user_id"])


@router.get("/settings")
async def settings(user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.settings, user["user_id"])


@router.put("/settings")
async def save_settings(request: RetrievalSettingsRequest, user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.save_settings, user["user_id"], request.to_config())


@router.post("/recall-test")
async def recall_test(request: RecallTestRequest, user: dict = Depends(get_current_user), service=Depends(get_memory_service)):
    return await invoke(service.recall_test, user["user_id"], request.query,
                        request.config.to_config() if request.config else None)
