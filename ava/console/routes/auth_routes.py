"""Authentication routes: login, refresh, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ava.console import auth
from ava.console.models import LoginRequest, LoginResponse, UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    from ava.console.app import get_services

    svc = get_services()
    user = svc.users.verify_password(body.username, body.password)
    if not user:
        svc.audit.log(
            user=body.username, role="unknown", action="auth.login_failed",
            target="", ip=get_client_ip(request),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = auth.create_access_token({"sub": user.username, "role": user.role, "created_at": user.created_at})
    svc.audit.log(
        user=user.username, role=user.role, action="auth.login",
        target="", ip=get_client_ip(request),
    )
    response = JSONResponse(LoginResponse(user=user).model_dump())
    auth.set_session_cookie(response, token)
    return response


@router.post("/refresh", response_model=LoginResponse)
async def refresh(user: UserInfo = Depends(auth.get_current_user)):
    token = auth.create_access_token({"sub": user.username, "role": user.role, "created_at": user.created_at})
    response = JSONResponse(LoginResponse(user=user).model_dump())
    auth.set_session_cookie(response, token)
    return response


@router.get("/me", response_model=UserInfo)
async def me(user: UserInfo = Depends(auth.get_current_user)):
    return user


@router.post("/logout")
async def logout():
    response = JSONResponse({"ok": True})
    auth.clear_session_cookie(response)
    return response
