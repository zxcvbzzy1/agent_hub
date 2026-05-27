from __future__ import annotations

from fastapi import APIRouter

from im_backend.api.routes import agents, artifacts, conversations, messages, rooms


router = APIRouter(prefix="/api/im", tags=["im"])
router.include_router(agents.router)
router.include_router(conversations.router)
router.include_router(rooms.router)
router.include_router(messages.router)
router.include_router(artifacts.router)
