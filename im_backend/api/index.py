from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from im_backend.api.core import get_container
from im_backend.api.auth_router import router as auth_router
from im_backend.api.router import router as im_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_container()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="IM Agent Platform API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(im_router)

    @app.get("/health")
    async def health():
        container = get_container()
        return {
            "status": "ok",
            "mongo": "memory" if container.store.using_memory else "mongodb",
            "service": "im_backend",
        }

    return app


app = create_app()
