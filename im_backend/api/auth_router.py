from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response

from im_backend.api.core import get_auth_service, get_current_token, get_current_user
from im_backend.api.schemas import LoginRequest, RegisterRequest
from im_backend.application.auth_service import AuthError, AuthService, DuplicateUserError


router = APIRouter(prefix="/api/im/auth", tags=["im-auth"])


def set_sse_cookie(response: Response, token: str, service: AuthService) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        "im_sse_session", token, max_age=service.session_remaining_seconds(token),
        httponly=True, samesite="lax", path="/api/im",
        secure=os.getenv("IM_SSE_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
    )


@router.post("/register")
async def register(request: RegisterRequest, response: Response, service: AuthService = Depends(get_auth_service)):
    try:
        item = service.register(
            username=request.username, email=request.email, password=request.password,
            display_name=request.display_name, avatar_url=request.avatar_url,
        )
        set_sse_cookie(response, item["token"], service)
        return {"item": item}
    except DuplicateUserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
async def login(request: LoginRequest, response: Response, service: AuthService = Depends(get_auth_service)):
    try:
        item = service.login(username=request.username, password=request.password)
        set_sse_cookie(response, item["token"], service)
        return {"item": item}
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me")
async def me(response: Response, current_user: dict = Depends(get_current_user),
             token: str = Depends(get_current_token), service: AuthService = Depends(get_auth_service)):
    set_sse_cookie(response, token, service)
    return {"item": current_user}


@router.post("/logout")
async def logout(
    response: Response,
    token: str = Depends(get_current_token),
    service: AuthService = Depends(get_auth_service),
):
    response.delete_cookie("im_sse_session", path="/api/im")
    response.headers["Cache-Control"] = "no-store"
    try:
        return {"item": service.logout(token)}
    except AuthError:
        response.status_code = 401
        return {"detail": "登录已失效"}
