"""Repo-backed mock bundle bootstrap for console mock_tester."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ava.agent.bg_tasks import TimelineEvent
from ava.storage.database import Database

LOCAL_ADMIN_USERNAME = "admin"
LOCAL_ADMIN_DEFAULT_PASSWORD = "admin"
MOCK_TESTER_USERNAME = "mock_tester"
LOCAL_ADMIN_PASSWORD_FILE = "admin_password"
MOCK_TESTER_PASSWORD_FILE = "mock_tester_password"
LOCAL_SECRETS_DIRNAME = "local-secrets"
MOCK_DATA_DIRNAME = "mock_data"
MOCK_DB_FILENAME = "mock.nanobot.db"
MOCK_BUNDLE_SIGNATURE_FILENAME = ".mock_bundle_signature"
DEFAULT_CONSOLE_SECRET = "change-me-in-production-use-a-longer-key!"


@dataclass
class LocalAccountInfo:
    username: str
    role: str
    password_file: Path


@dataclass
class MockBundleRuntime:
    root: Path
    workspace: Path
    media_dir: Path
    db_path: Path
    template_dir: Path


class MockGatewayService:
    """Static gateway state for mock_tester."""

    def __init__(self, console_port: int) -> None:
        self._console_port = console_port

    def get_status(self) -> dict[str, Any]:
        return {
            "running": True,
            "pid": 4242,
            "uptime_seconds": 7322,
            "gateway_port": 18790,
            "console_port": self._console_port,
            "supervised": True,
            "supervisor": "mock-runtime",
            "restart_pending": False,
            "boot_generation": 7,
            "last_exit_reason": None,
        }

    def health(self) -> dict[str, Any]:
        return {"ok": True, "mode": "mock"}


class MockBackgroundTaskStore:
    """Static-yet-mutable mock bg task store for console preview pages."""

    def __init__(self, seed: dict[str, Any] | None = None) -> None:
        payload = seed or _load_mock_seed()
        self._active = {
            item["task_id"]: self._normalize_task(item)
            for item in payload.get("bg_tasks_active", [])
        }
        self._history = {
            item["task_id"]: self._normalize_task(item)
            for item in payload.get("bg_tasks_history", [])
        }

    @staticmethod
    def _normalize_task(item: dict[str, Any]) -> dict[str, Any]:
        task = dict(item)
        task.setdefault("elapsed_ms", 0)
        task.setdefault("result_preview", "")
        task.setdefault("error_message", "")
        task.setdefault("phase", "")
        task.setdefault("last_tool_name", "")
        task.setdefault("todo_summary", None)
        task.setdefault("project_path", "")
        task.setdefault("cli_session_id", "")
        task.setdefault("timeline", [])
        task.setdefault("full_prompt", "")
        task.setdefault("full_result", "")
        return task

    @staticmethod
    def _public_task(task: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in task.items()
            if key not in {"full_prompt", "full_result"}
        }

    def _filtered_tasks(
        self,
        *,
        task_id: str | None = None,
        session_key: str | None = None,
        task_type: str | None = None,
        include_finished: bool = True,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        if task_id:
            task = self._active.get(task_id) or self._history.get(task_id)
            if task:
                tasks.append(task)
        else:
            tasks.extend(self._active.values())
            if include_finished:
                tasks.extend(self._history.values())

        if session_key:
            tasks = [task for task in tasks if task.get("origin_session_key") == session_key]
        if task_type:
            tasks = [task for task in tasks if task.get("task_type") == task_type]
        tasks.sort(key=lambda task: float(task.get("started_at") or 0), reverse=True)
        return tasks

    def get_status(
        self,
        task_id: str | None = None,
        session_key: str | None = None,
        task_type: str | None = None,
        include_finished: bool = True,
        verbose: bool = False,
    ) -> dict[str, Any]:
        tasks = self._filtered_tasks(
            task_id=task_id,
            session_key=session_key,
            task_type=task_type,
            include_finished=include_finished,
        )
        running = sum(1 for task in tasks if task.get("status") in {"queued", "running"})
        return {
            "running": running,
            "total": len(tasks),
            "tasks": [self._public_task(task) for task in tasks],
        }

    def query_history(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        tasks = list(self._history.values())
        if session_key:
            tasks = [task for task in tasks if task.get("origin_session_key") == session_key]
        tasks.sort(key=lambda task: float(task.get("started_at") or 0), reverse=True)
        total = len(tasks)
        offset = max(page - 1, 0) * page_size
        paged = tasks[offset: offset + page_size]
        return {
            "tasks": [self._public_task(task) for task in paged],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_task_detail(self, task_id: str) -> dict[str, Any] | None:
        task = self._active.get(task_id) or self._history.get(task_id)
        if not task:
            return None
        return {
            "task_id": task_id,
            "full_prompt": str(task.get("full_prompt") or ""),
            "full_result": str(task.get("full_result") or ""),
        }

    def get_timeline(self, task_id: str) -> list[TimelineEvent]:
        task = self._active.get(task_id) or self._history.get(task_id)
        if not task:
            return []
        return [
            TimelineEvent(
                timestamp=float(event.get("timestamp") or 0),
                event=str(event.get("event") or ""),
                detail=str(event.get("detail") or ""),
            )
            for event in task.get("timeline", [])
        ]

    async def cancel(self, task_id: str) -> str:
        task = self._active.pop(task_id, None)
        if task is None:
            if task_id in self._history:
                return f"Task {task_id} already finished."
            return f"Task {task_id} not found."

        now = time.time()
        started_at = float(task.get("started_at") or now)
        task["status"] = "cancelled"
        task["finished_at"] = now
        task["elapsed_ms"] = int(max(now - started_at, 0) * 1000)
        task["error_message"] = str(task.get("error_message") or "Cancelled in mock mode.")
        task.setdefault("timeline", []).append({
            "timestamp": now,
            "event": "cancelled",
            "detail": "Cancelled from mock console",
        })
        self._history[task_id] = task
        return f"Task {task_id} cancelled."


def bundle_template_dir() -> Path:
    return Path(__file__).parent / "mock_bundle"


def local_secrets_dir(console_dir: Path) -> Path:
    return console_dir / LOCAL_SECRETS_DIRNAME


def mock_runtime_dir(console_dir: Path) -> Path:
    return console_dir / MOCK_DATA_DIRNAME


def ensure_local_accounts(users, console_dir: Path) -> dict[str, LocalAccountInfo]:
    secrets_dir = local_secrets_dir(console_dir)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    _best_effort_private_dir(secrets_dir)

    admin = _ensure_local_account(
        users=users,
        secrets_dir=secrets_dir,
        username=LOCAL_ADMIN_USERNAME,
        role="admin",
        password_filename=LOCAL_ADMIN_PASSWORD_FILE,
        default_password=LOCAL_ADMIN_DEFAULT_PASSWORD,
    )
    mock = _ensure_local_account(
        users=users,
        secrets_dir=secrets_dir,
        username=MOCK_TESTER_USERNAME,
        role="mock_tester",
        password_filename=MOCK_TESTER_PASSWORD_FILE,
    )
    return {
        admin.username: admin,
        mock.username: mock,
    }


def validate_console_security(console_cfg: Any, console_host: str) -> None:
    if not bool(getattr(console_cfg, "public_dev", False)):
        return

    secret_key = str(getattr(console_cfg, "secret_key", "") or "")
    if secret_key == DEFAULT_CONSOLE_SECRET or len(secret_key) < 32:
        raise RuntimeError("gateway.console.public_dev=true requires a strong secretKey")

    expire_minutes = int(getattr(console_cfg, "token_expire_minutes", 0) or 0)
    if expire_minutes <= 0 or expire_minutes > 60:
        raise RuntimeError("gateway.console.public_dev=true requires tokenExpireMinutes <= 60")

    if console_host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("gateway.console.public_dev=true only allows localhost origin binding")

    if not bool(getattr(console_cfg, "session_cookie_secure", False)):
        raise RuntimeError("gateway.console.public_dev=true requires secure session cookie")

    if not str(getattr(console_cfg, "cloudflare_access_team_domain", "") or "").strip():
        raise RuntimeError("gateway.console.public_dev=true requires cloudflareAccessTeamDomain")

    if not str(getattr(console_cfg, "cloudflare_access_audience", "") or "").strip():
        raise RuntimeError("gateway.console.public_dev=true requires cloudflareAccessAudience")


def prepare_mock_runtime(console_dir: Path, console_port: int) -> MockBundleRuntime:
    template_dir = bundle_template_dir()
    runtime_root = mock_runtime_dir(console_dir)
    template_signature = _compute_template_signature(template_dir)
    signature_path = runtime_root / MOCK_BUNDLE_SIGNATURE_FILENAME
    runtime_exists = runtime_root.exists()
    runtime_signature = _read_runtime_signature(signature_path)

    if runtime_exists and runtime_signature != template_signature:
        shutil.rmtree(runtime_root)

    runtime_root.mkdir(parents=True, exist_ok=True)
    _sync_template_tree(template_dir, runtime_root)
    signature_path.write_text(template_signature + "\n", "utf-8")

    media_dir = runtime_root / "media" / "generated"
    media_dir.mkdir(parents=True, exist_ok=True)
    db_path = runtime_root / MOCK_DB_FILENAME

    _seed_media_assets(media_dir)
    db = Database(db_path)
    _seed_mock_db(db, console_port=console_port, media_dir=media_dir)

    return MockBundleRuntime(
        root=runtime_root,
        workspace=runtime_root / "workspace",
        media_dir=media_dir,
        db_path=db_path,
        template_dir=template_dir,
    )


def _ensure_local_account(
    *,
    users,
    secrets_dir: Path,
    username: str,
    role: str,
    password_filename: str,
    default_password: str | None = None,
) -> LocalAccountInfo:
    password_file = secrets_dir / password_filename
    password = _ensure_password_file(password_file, default_password=default_password)

    existing = users.get_user(username)
    if existing is None:
        users.create_user(username, password, role)
    else:
        password_matches = users.verify_password(username, password) is not None
        needs_role = existing.role != role
        if not password_matches or needs_role:
            users.update_user(
                username,
                password=password if not password_matches else None,
                role=role if needs_role else None,
            )

    return LocalAccountInfo(username=username, role=role, password_file=password_file)


def _ensure_password_file(path: Path, default_password: str | None = None) -> str:
    if path.exists():
        password = path.read_text("utf-8").strip()
        if password:
            return password

    password = default_password if default_password is not None else secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password + "\n", "utf-8")
    _best_effort_private_file(path)
    return password


def _best_effort_private_dir(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _best_effort_private_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _sync_template_tree(template_dir: Path, runtime_root: Path) -> None:
    if not template_dir.is_dir():
        raise RuntimeError(f"Mock bundle template not found: {template_dir}")

    for source in template_dir.rglob("*"):
        relative = source.relative_to(template_dir)
        target = runtime_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)


def _seed_media_assets(media_dir: Path) -> None:
    seed = _load_mock_seed()
    for asset in seed.get("media_assets", []):
        name = str(asset.get("name", "")).strip()
        encoded = str(asset.get("content_base64", "")).strip()
        if not name or not encoded:
            continue
        path = media_dir / name
        if path.exists():
            continue
        path.write_bytes(base64.b64decode(encoded))


def _seed_mock_db(db: Database, *, console_port: int, media_dir: Path) -> None:
    seed = _load_mock_seed()
    media_rows = seed.get("media_records", [])
    if _table_count(db, "media_records") == 0:
        for row in media_rows:
            db.execute(
                """INSERT INTO media_records
                   (id, timestamp, prompt, reference_image, output_images, output_text, model, status, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"],
                    row["timestamp"],
                    row["prompt"],
                    row.get("reference_image"),
                    json.dumps(row.get("output_images", []), ensure_ascii=False),
                    row.get("output_text", ""),
                    row.get("model", ""),
                    row.get("status", "success"),
                    row.get("error"),
                ),
            )

    if _table_count(db, "audit_entries") == 0:
        for row in seed.get("audit_entries", []):
            db.execute(
                """INSERT INTO audit_entries
                   (timestamp, user, role, action, target, detail, ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["timestamp"],
                    row["user"],
                    row["role"],
                    row["action"],
                    row["target"],
                    json.dumps(row.get("detail"), ensure_ascii=False) if row.get("detail") else None,
                    row.get("ip", ""),
                ),
            )

    if _table_count(db, "sessions") == 0:
        for session in seed.get("sessions", []):
            db.execute(
                """INSERT INTO sessions
                   (key, created_at, updated_at, metadata, last_consolidated, last_completed, token_stats)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session["key"],
                    session["created_at"],
                    session["updated_at"],
                    json.dumps(session.get("metadata", {}), ensure_ascii=False),
                    session.get("last_consolidated", 0),
                    session.get("last_completed"),
                    json.dumps(session.get("token_stats", {}), ensure_ascii=False),
                ),
            )
        db.commit()
        for msg in seed.get("session_messages", []):
            session_row = db.fetchone("SELECT id FROM sessions WHERE key = ?", (msg["session_key"],))
            if not session_row:
                continue
            db.execute(
                """INSERT INTO session_messages
                   (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_row["id"],
                    msg["seq"],
                    msg.get("conversation_id", ""),
                    msg["role"],
                    _encode_message_content(msg.get("content", "")),
                    json.dumps(msg.get("tool_calls"), ensure_ascii=False) if msg.get("tool_calls") else None,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                    msg.get("reasoning_content"),
                    msg.get("timestamp"),
                ),
            )

    if _table_count(db, "token_usage") == 0:
        for row in seed.get("token_usage", []):
            db.execute(
                """INSERT INTO token_usage
                   (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                    session_key, conversation_id, turn_seq, iteration, user_message, output_content,
                    system_prompt_preview, conversation_history, full_request_payload, finish_reason,
                    model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens, tool_names)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["timestamp"],
                    row["model"],
                    row["provider"],
                    row["prompt_tokens"],
                    row["completion_tokens"],
                    row["total_tokens"],
                    row.get("session_key", ""),
                    row.get("conversation_id", ""),
                    row.get("turn_seq"),
                    row.get("iteration", 0),
                    row.get("user_message", ""),
                    row.get("output_content", ""),
                    row.get("system_prompt_preview", ""),
                    row.get("conversation_history", ""),
                    row.get("full_request_payload", ""),
                    row.get("finish_reason", ""),
                    row.get("model_role", "default"),
                    row.get("cached_tokens", 0),
                    row.get("cache_creation_tokens", 0),
                    row.get("cost_usd", 0.0),
                    row.get("current_turn_tokens", 0),
                    row.get("tool_names", ""),
                ),
            )

    if _table_count(db, "skill_config") == 0:
        for row in seed.get("skill_config", []):
            db.execute(
                """INSERT INTO skill_config
                   (name, source, enabled, installed_at, install_method, git_url, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["name"],
                    row.get("source", "ava"),
                    int(row.get("enabled", 1)),
                    row.get("installed_at"),
                    row.get("install_method"),
                    row.get("git_url"),
                    row.get("updated_at"),
                ),
            )

    db.commit()

    version_row = db.fetchone("SELECT version FROM schema_version LIMIT 1")
    if version_row is None:
        db.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
        db.commit()

    status_file = media_dir.parent.parent / "gateway_status.json"
    if not status_file.exists():
        status_file.write_text(
            json.dumps(
                {
                    "running": True,
                    "consolePort": console_port,
                    "supervisor": "mock-runtime",
                },
                indent=2,
                ensure_ascii=False,
            ),
            "utf-8",
        )


def _table_count(db: Database, table: str) -> int:
    row = db.fetchone(f"SELECT COUNT(*) as cnt FROM {table}")
    return int(row["cnt"]) if row else 0


def _encode_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def _load_mock_seed() -> dict[str, Any]:
    path = bundle_template_dir() / "mock_seed.json"
    return json.loads(path.read_text("utf-8"))


def _compute_template_signature(template_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in template_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(template_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_runtime_signature(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text("utf-8").strip()
