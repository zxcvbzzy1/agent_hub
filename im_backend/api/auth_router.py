from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from im_backend.api.core import get_auth_service, get_current_token, get_current_user
from im_backend.api.schemas import LoginRequest, RegisterRequest
from im_backend.application.auth_service import AuthError, AuthService, DuplicateUserError


router = APIRouter(prefix="/api/im/auth", tags=["im-auth"])


@router.post("/register")
async def register(request: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return {
            "item": service.register(
                username=request.username,
                email=request.email,
                password=request.password,
                display_name=request.display_name,
                avatar_url=request.avatar_url,
            )
        }
    except DuplicateUserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
async def login(request: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        return {"item": service.login(username=request.username, password=request.password)}
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"item": current_user}


@router.post("/logout")
async def logout(
    token: str = Depends(get_current_token),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return {"item": service.logout(token)}
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
