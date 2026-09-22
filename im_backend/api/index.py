from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from im_backend.api.core import get_container
from im_backend.api.auth_router import router as auth_router
from im_backend.api.router import router as im_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = get_container()
    await container.bridge.runtime.start()

    async def cleanup_files():
        while True:
            await asyncio.sleep(3600)
            try:
                await container.files.sweep()
            except Exception:
                logging.getLogger(__name__).exception("File cleanup failed; will retry")

    task = None
    try:
        await container.files.sweep()
        task = asyncio.create_task(cleanup_files())
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await container.bridge.runtime.close()


def create_app() -> FastAPI:
    app = FastAPI(title="IM Agent Platform API", lifespan=lifespan)

    @app.exception_handler(PyMongoError)
    async def database_unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "数据库不可用，请稍后重试"})
    @app.exception_handler(RedisError)
    async def redis_unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Redis 运行时不可用"})

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
        container.store.ping()
        await container.bridge.runtime.redis.ping()
        return {
            "status": "ok",
            "mongo": "mongodb",
            "redis": "ok",
            "service": "im_backend",
        }

    return app


app = create_app()
