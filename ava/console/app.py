"""FastAPI application factory and service container."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from loguru import logger
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from ava.adapters.nanobot.discovery import resolve_nanobot_checkout
from ava.console import auth
from ava.console.middleware import setup_cors
from ava.console.mock_bundle_runtime import (
    MockBackgroundTaskStore,
    MockGatewayService,
    ensure_local_accounts,
    prepare_mock_runtime,
)
from ava.console.models import UserInfo
from ava.console.ui_build import prepare_console_ui_dist
from ava.console.services.audit_service import AuditService
from ava.console.services.chat_service import ChatService
from ava.console.services.config_service import ConfigService
from ava.console.services.file_service import FileService
from ava.console.services.gateway_service import GatewayService
from ava.console.services.media_service import MediaService
from ava.console.services.skills_service import SkillsService
from ava.console.services.token_stats_service import TokenStatsCollector
from ava.console.services.trace_spans_service import TraceSpanStore
from ava.console.services.user_service import UserService


@dataclass
class Services:
    users: UserService
    audit: AuditService
    config: ConfigService
    files: FileService
    gateway: GatewayService | MockGatewayService
    media: MediaService
    skills: SkillsService
    chat: ChatService | None = None
    token_stats: TokenStatsCollector | None = None
    trace_spans: TraceSpanStore | None = None
    mock: "Services | None" = None


_services: Services | None = None


def get_services() -> Services:
    if _services is None:
        raise RuntimeError("Console services not initialized")
    return _services


def get_services_for_user(user: UserInfo | None = None) -> Services:
    services = get_services()
    if user and user.role == "mock_tester" and services.mock is not None:
        return services.mock
    return services


def _proxy_close_params(
    code: object | None,
    reason: object | None,
    *,
    fallback_code: int = 1000,
    fallback_reason: str = "",
) -> tuple[int, str]:
    close_code = code if isinstance(code, int) and code > 0 else fallback_code
    close_reason = reason if isinstance(reason, str) else ""
    if not close_reason:
        close_reason = fallback_reason
    return close_code, close_reason


async def _close_upstream_if_needed(upstream, *, code: int, reason: str) -> None:
    try:
        await upstream.close(code=code, reason=reason)
    except TypeError:
        await upstream.close()
    except Exception:
        pass


async def _close_websocket_if_needed(websocket: WebSocket, *, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass


def _mount_console_spa(app: FastAPI) -> None:
    static_dir = prepare_console_ui_dist()
    if not static_dir:
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    index_html = static_dir / "index.html"

    _NO_CACHE_FILES = {"index.html", "version.json"}

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        file_path = static_dir / full_path
        if file_path.is_file():
            resp = FileResponse(file_path)
            if file_path.name in _NO_CACHE_FILES:
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return resp
        resp = FileResponse(index_html)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


def create_console_app(
    nanobot_dir: Path,
    workspace: Path,
    agent_loop,
    config,
    token_stats_collector: TokenStatsCollector | None = None,
    db=None,
) -> FastAPI:
    global _services

    console_dir = nanobot_dir / "console"
    console_dir.mkdir(parents=True, exist_ok=True)

    console_cfg = config.gateway.console
    auth.configure(
        secret_key=console_cfg.secret_key,
        expire_minutes=console_cfg.token_expire_minutes,
        cookie_name=getattr(console_cfg, "session_cookie_name", "ava_console_session"),
        cookie_secure=bool(getattr(console_cfg, "session_cookie_secure", False)),
        cookie_samesite=str(getattr(console_cfg, "session_cookie_samesite", "lax")),
    )

    skill_dir = Path(__file__).parent.parent / "skills"
    upstream_skills_dir = resolve_nanobot_checkout().skills_dir

    lifecycle_mgr = getattr(agent_loop, "lifecycle_manager", None) if agent_loop else None

    users = UserService(console_dir)
    ensure_local_accounts(users, console_dir)
    mock_runtime = prepare_mock_runtime(console_dir, console_cfg.port)
    from ava.storage import Database
    mock_db = Database(mock_runtime.db_path)
    trace_spans = TraceSpanStore(db) if db is not None else None
    if token_stats_collector is not None:
        token_stats_collector._trace_spans = trace_spans
    mock_trace_spans = TraceSpanStore(mock_db) if mock_db is not None else None

    real_services = Services(
        users=users,
        audit=AuditService(console_dir, db=db),
        config=ConfigService(nanobot_dir),
        files=FileService(workspace, nanobot_dir),
        gateway=GatewayService(
            lifecycle=lifecycle_mgr,
            gateway_port=config.gateway.port,
            console_port=console_cfg.port,
        ),
        media=MediaService(db=db),
        skills=SkillsService(
            workspace,
            skill_dir,
            nanobot_dir,
            upstream_skills_dir=upstream_skills_dir,
            db=db,
        ),
        chat=ChatService(agent_loop, workspace, db=db),
        token_stats=token_stats_collector,
        trace_spans=trace_spans,
    )
    if trace_spans is not None:
        trace_spans.mark_interrupted(stale_threshold_ns=30 * 60 * 1_000_000_000)
    mock_chat = ChatService(agent_loop=None, workspace=mock_runtime.workspace, db=mock_db)
    mock_chat._agent = SimpleNamespace(bg_tasks=MockBackgroundTaskStore())

    real_services.mock = Services(
        users=users,
        audit=AuditService(mock_runtime.root, db=mock_db),
        config=ConfigService(mock_runtime.root),
        files=FileService(mock_runtime.workspace, mock_runtime.root),
        gateway=MockGatewayService(console_cfg.port),
        media=MediaService(
            media_dir=mock_runtime.media_dir,
            screenshot_dir=mock_runtime.media_dir.parent / "screenshots",
            db=mock_db,
        ),
        skills=SkillsService(
            mock_runtime.workspace,
            skill_dir,
            mock_runtime.root,
            upstream_skills_dir=upstream_skills_dir,
            db=mock_db,
        ),
        chat=mock_chat,
        token_stats=TokenStatsCollector(
            data_dir=mock_runtime.root,
            db=mock_db,
            trace_spans=mock_trace_spans,
        ) if mock_db is not None else None,
        trace_spans=mock_trace_spans,
    )
    _services = real_services

    app = FastAPI(
        title="Nanobot Console",
        description="Web management console for Nanobot",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    setup_cors(app)

    from ava.console.routes import (
        auth_routes,
        config_routes,
        file_routes,
        gateway_routes,
        chat_routes,
        media_routes,
        user_routes,
        audit_routes,
        token_routes,
        trace_routes,
        skills_routes,
        page_agent_routes,
    )
    from ava.console.routes import bg_task_routes

    app.include_router(auth_routes.router)
    app.include_router(config_routes.router)
    app.include_router(file_routes.router)
    app.include_router(gateway_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(media_routes.router)
    app.include_router(user_routes.router)
    app.include_router(audit_routes.router)
    app.include_router(token_routes.router)
    app.include_router(trace_routes.router)
    app.include_router(skills_routes.router)
    app.include_router(page_agent_routes.router)
    app.include_router(bg_task_routes.router)

    _mount_console_spa(app)

    return app


def create_console_app_standalone(
    nanobot_dir: Path,
    workspace: Path,
    gateway_port: int = 18790,
    console_port: int = 6688,
    secret_key: str = "change-me-in-production",
    expire_minutes: int = 480,
    session_cookie_name: str = "ava_console_session",
    session_cookie_secure: bool = False,
    session_cookie_samesite: str = "lax",
    token_stats_dir: str = "",
) -> FastAPI:
    """Create a console app that runs independently from the gateway process.

    This variant does not require a live AgentLoop — ChatService is set to None,
    and TokenStatsCollector reads from the shared SQLite DB (or JSON file fallback).
    """
    global _services

    console_dir = nanobot_dir / "console"
    console_dir.mkdir(parents=True, exist_ok=True)

    auth.configure(
        secret_key=secret_key,
        expire_minutes=expire_minutes,
        cookie_name=session_cookie_name,
        cookie_secure=session_cookie_secure,
        cookie_samesite=session_cookie_samesite,
    )

    skill_dir = Path(__file__).parent.parent / "skills"
    upstream_skills_dir = resolve_nanobot_checkout().skills_dir

    users = UserService(console_dir)
    ensure_local_accounts(users, console_dir)

    db_path = nanobot_dir / "nanobot.db"
    from ava.storage import Database
    db = Database(db_path)
    mock_runtime = prepare_mock_runtime(console_dir, console_port)
    mock_db = Database(mock_runtime.db_path)
    trace_spans = TraceSpanStore(db)
    mock_trace_spans = TraceSpanStore(mock_db)

    token_stats = None
    if token_stats_dir:
        token_stats = TokenStatsCollector(data_dir=Path(token_stats_dir), db=db, trace_spans=trace_spans)

    real_services = Services(
        users=users,
        audit=AuditService(console_dir, db=db),
        config=ConfigService(nanobot_dir),
        files=FileService(workspace, nanobot_dir),
        gateway=GatewayService(
            gateway_port=gateway_port,
            console_port=console_port,
        ),
        media=MediaService(db=db),
        skills=SkillsService(
            workspace,
            skill_dir,
            nanobot_dir,
            upstream_skills_dir=upstream_skills_dir,
            db=db,
        ),
        chat=None,  # type: ignore[arg-type]
        token_stats=token_stats,
        trace_spans=trace_spans,
    )
    trace_spans.mark_interrupted(stale_threshold_ns=30 * 60 * 1_000_000_000)
    mock_chat = ChatService(agent_loop=None, workspace=mock_runtime.workspace, db=mock_db)
    mock_chat._agent = SimpleNamespace(bg_tasks=MockBackgroundTaskStore())

    real_services.mock = Services(
        users=users,
        audit=AuditService(mock_runtime.root, db=mock_db),
        config=ConfigService(mock_runtime.root),
        files=FileService(mock_runtime.workspace, mock_runtime.root),
        gateway=MockGatewayService(console_port),
        media=MediaService(
            media_dir=mock_runtime.media_dir,
            screenshot_dir=mock_runtime.media_dir.parent / "screenshots",
            db=mock_db,
        ),
        skills=SkillsService(
            mock_runtime.workspace,
            skill_dir,
            mock_runtime.root,
            upstream_skills_dir=upstream_skills_dir,
            db=mock_db,
        ),
        chat=mock_chat,
        token_stats=TokenStatsCollector(data_dir=mock_runtime.root, db=mock_db, trace_spans=mock_trace_spans),
        trace_spans=mock_trace_spans,
    )
    _services = real_services

    app = FastAPI(
        title="Nanobot Console",
        description="Web management console for Nanobot (standalone)",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    setup_cors(app)

    from ava.console.routes import (
        auth_routes,
        config_routes,
        file_routes,
        gateway_routes,
        media_routes,
        user_routes,
        audit_routes,
        token_routes,
        trace_routes,
        skills_routes,
    )
    from ava.console.routes import bg_task_routes

    app.include_router(auth_routes.router)
    app.include_router(config_routes.router)
    app.include_router(file_routes.router)
    app.include_router(gateway_routes.router)
    app.include_router(media_routes.router)
    app.include_router(user_routes.router)
    app.include_router(audit_routes.router)
    app.include_router(token_routes.router)
    app.include_router(trace_routes.router)
    app.include_router(skills_routes.router)
    app.include_router(bg_task_routes.router)

    # --- Chat reverse proxy to gateway ----------------------------------
    gateway_base = f"http://127.0.0.1:{gateway_port}"

    @app.api_route(
        "/api/chat/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    async def proxy_chat_http(request: Request, path: str):
        import httpx
        target = f"{gateway_base}/api/chat/{path}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        body = await request.body()
        try:
            # trust_env=False to ignore system proxy settings (e.g. Clash on port 7897)
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                resp = await client.request(
                    method=request.method,
                    url=target,
                    headers={
                        k: v for k, v in request.headers.items()
                        if k.lower() not in ("host", "content-length")
                    },
                    content=body,
                )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
        except httpx.ConnectError:
            return Response(
                content='{"detail":"Gateway offline — chat unavailable"}',
                status_code=503,
                media_type="application/json",
            )

    @app.websocket("/api/chat/ws/{session_id}")
    async def proxy_chat_ws(websocket: WebSocket, session_id: str):
        import websockets.asyncio.client as ws_client
        from websockets import exceptions as ws_exceptions

        await websocket.accept()
        cookie_name = auth.session_cookie_name()
        cookie_value = websocket.cookies.get(cookie_name, "")
        gw_ws_url = f"ws://127.0.0.1:{gateway_port}/api/chat/ws/{session_id}"
        try:
            connect_kwargs = {}
            if cookie_value:
                connect_kwargs["additional_headers"] = {
                    "Cookie": f"{cookie_name}={cookie_value}",
                }
            async with ws_client.connect(gw_ws_url, **connect_kwargs) as upstream:

                async def client_to_upstream():
                    close_code = 1000
                    close_reason = ""
                    try:
                        while True:
                            data = await websocket.receive_text()
                            await upstream.send(data)
                    except WebSocketDisconnect as exc:
                        close_code, close_reason = _proxy_close_params(
                            getattr(exc, "code", None),
                            getattr(exc, "reason", ""),
                        )
                        logger.debug(
                            "proxy_chat_ws client->upstream disconnected for {}: code={} reason={}",
                            session_id,
                            close_code,
                            close_reason,
                        )
                    except Exception as exc:
                        logger.debug(
                            "proxy_chat_ws client->upstream error for {}: {}",
                            session_id,
                            exc,
                        )
                        raise
                    finally:
                        await _close_upstream_if_needed(
                            upstream,
                            code=close_code,
                            reason=close_reason,
                        )
                        logger.debug(
                            "proxy_chat_ws client->upstream finished for {} (upstream_state={} close_code={} close_reason={})",
                            session_id,
                            getattr(upstream, "state", None),
                            getattr(upstream, "close_code", None),
                            getattr(upstream, "close_reason", None),
                        )

                async def upstream_to_client():
                    close_code = 1000
                    close_reason = ""
                    try:
                        async for msg in upstream:
                            await websocket.send_text(msg if isinstance(msg, str) else msg.decode())
                        close_code, close_reason = _proxy_close_params(
                            getattr(upstream, "close_code", None),
                            getattr(upstream, "close_reason", None),
                        )
                        logger.debug(
                            "proxy_chat_ws upstream->client stream ended for {} (close_code={} close_reason={})",
                            session_id,
                            close_code,
                            close_reason,
                        )
                    except ws_exceptions.ConnectionClosed as exc:
                        close_code, close_reason = _proxy_close_params(
                            getattr(exc, "code", None),
                            getattr(exc, "reason", ""),
                        )
                        logger.debug(
                            "proxy_chat_ws upstream->client disconnected for {}: code={} reason={}",
                            session_id,
                            close_code,
                            close_reason,
                        )
                    except Exception as exc:
                        logger.debug(
                            "proxy_chat_ws upstream->client error for {}: {}",
                            session_id,
                            exc,
                        )
                        raise
                    finally:
                        await _close_websocket_if_needed(
                            websocket,
                            code=close_code,
                            reason=close_reason,
                        )
                        logger.debug(
                            "proxy_chat_ws upstream->client finished for {} (close_code={} close_reason={})",
                            session_id,
                            close_code,
                            close_reason,
                        )

                await asyncio.gather(client_to_upstream(), upstream_to_client())
        except Exception as exc:
            logger.debug("proxy_chat_ws outer exception for {}: {}", session_id, exc)
            try:
                await websocket.close(code=1011, reason="Gateway unreachable")
            except Exception:
                pass

    # --- End chat proxy -------------------------------------------------

    _mount_console_spa(app)

    return app
