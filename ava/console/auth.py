"""JWT authentication and role-based access control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, Response, status, WebSocket, WebSocketException

from ava.console.models import UserInfo

_secret_key: str = "change-me"
_algorithm: str = "HS256"
_expire_minutes: int = 480
_cookie_name: str = "ava_console_session"
_cookie_secure: bool = False
_cookie_samesite: str = "lax"


def configure(
    secret_key: str,
    expire_minutes: int = 480,
    *,
    cookie_name: str = "ava_console_session",
    cookie_secure: bool = False,
    cookie_samesite: str = "lax",
) -> None:
    global _secret_key, _expire_minutes, _cookie_name, _cookie_secure, _cookie_samesite
    _secret_key = secret_key
    _expire_minutes = expire_minutes
    _cookie_name = cookie_name
    _cookie_secure = cookie_secure
    _cookie_samesite = cookie_samesite.lower()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=_expire_minutes))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, _secret_key, algorithm=_algorithm)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret_key, algorithms=[_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def session_cookie_name() -> str:
    return _cookie_name


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_cookie_name,
        value=token,
        httponly=True,
        secure=_cookie_secure,
        samesite=_cookie_samesite,
        max_age=_expire_minutes * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=_cookie_name, path="/")


def _user_from_payload(payload: dict) -> UserInfo:
    username = payload.get("sub")
    role = payload.get("role")
    created_at = payload.get("created_at", "")
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return UserInfo(username=username, role=role, created_at=created_at)


def _request_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return request.cookies.get(_cookie_name)


def _ws_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return websocket.cookies.get(_cookie_name)


async def get_current_user(request: Request) -> UserInfo:
    token = _request_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = verify_token(token)
    return _user_from_payload(payload)


async def get_ws_user(websocket: WebSocket) -> UserInfo:
    """Extract user from WebSocket cookie or Authorization header."""
    token = _ws_token(websocket)
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = verify_token(token)
    except HTTPException as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc

    username = payload.get("sub")
    role = payload.get("role")
    created_at = payload.get("created_at", "")
    if not username or not role:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return UserInfo(username=username, role=role, created_at=created_at)


async def optional_user(request: Request) -> UserInfo | None:
    """Return user if valid token is present, None otherwise."""
    token = _request_token(request)
    if not token:
        return None
    try:
        payload = verify_token(token)
        return _user_from_payload(payload)
    except HTTPException:
        return None


def require_role(*allowed_roles: str) -> Callable:
    """Dependency that checks if current user has one of the allowed roles."""

    async def checker(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not allowed. Required: {', '.join(allowed_roles)}",
            )
        return user

    return checker
