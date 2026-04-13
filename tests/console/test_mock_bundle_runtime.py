from __future__ import annotations

from types import SimpleNamespace

import pytest

from ava.console.mock_bundle_runtime import (
    LOCAL_ADMIN_PASSWORD_FILE,
    LOCAL_ADMIN_USERNAME,
    MockBackgroundTaskStore,
    MOCK_TESTER_PASSWORD_FILE,
    MOCK_TESTER_USERNAME,
    ensure_local_accounts,
    prepare_mock_runtime,
    validate_console_security,
)
from ava.console.services.user_service import UserService
from ava.storage import Database


def test_ensure_local_accounts_creates_local_password_files(tmp_path):
    console_dir = tmp_path / "console"
    users = UserService(console_dir)

    accounts = ensure_local_accounts(users, console_dir)

    assert set(accounts) == {LOCAL_ADMIN_USERNAME, MOCK_TESTER_USERNAME}
    assert (console_dir / "local-secrets" / LOCAL_ADMIN_PASSWORD_FILE).is_file()
    assert (console_dir / "local-secrets" / MOCK_TESTER_PASSWORD_FILE).is_file()
    assert users.get_user(LOCAL_ADMIN_USERNAME) is not None
    assert users.get_user(MOCK_TESTER_USERNAME) is not None
    assert users.get_user(MOCK_TESTER_USERNAME).role == "mock_tester"


def test_prepare_mock_runtime_copies_markdown_and_seeds_db(tmp_path):
    runtime = prepare_mock_runtime(tmp_path / "console", console_port=6688)

    assert (runtime.workspace / "AGENTS.md").is_file()
    assert (runtime.workspace / "memory" / "MEMORY.md").is_file()
    assert runtime.db_path.is_file()

    db = Database(runtime.db_path)
    assert db.fetchone("SELECT COUNT(*) AS cnt FROM media_records")["cnt"] >= 2
    assert db.fetchone("SELECT COUNT(*) AS cnt FROM token_usage")["cnt"] >= 2
    assert db.fetchone("SELECT COUNT(*) AS cnt FROM session_messages")["cnt"] >= 2


def test_prepare_mock_runtime_rebuilds_legacy_runtime_without_signature(tmp_path):
    console_dir = tmp_path / "console"
    runtime = prepare_mock_runtime(console_dir, console_port=6688)
    db = Database(runtime.db_path)

    db.execute("DELETE FROM token_usage")
    db.execute("DELETE FROM session_messages")
    db.execute("DELETE FROM sessions WHERE key != ?", ("console:mock-session-1",))
    db.execute("UPDATE sessions SET token_stats = '{}' WHERE key = ?", ("console:mock-session-1",))
    db.commit()

    signature_path = runtime.root / ".mock_bundle_signature"
    signature_path.unlink()

    refreshed = prepare_mock_runtime(console_dir, console_port=6688)
    refreshed_db = Database(refreshed.db_path)

    assert refreshed_db.fetchone("SELECT COUNT(*) AS cnt FROM sessions")["cnt"] >= 3
    assert refreshed_db.fetchone("SELECT COUNT(*) AS cnt FROM session_messages")["cnt"] >= 9
    assert refreshed_db.fetchone("SELECT COUNT(*) AS cnt FROM token_usage")["cnt"] >= 9


def test_mock_background_task_store_exposes_active_and_history_samples():
    store = MockBackgroundTaskStore()

    active = store.get_status(include_finished=False)
    assert {task["status"] for task in active["tasks"]} == {"queued", "running"}

    history = store.query_history(page=1, page_size=10)
    assert {"succeeded", "failed", "cancelled"} <= {task["status"] for task in history["tasks"]}


@pytest.mark.parametrize(
    ("secret_key", "expire_minutes", "host", "cookie_secure", "team_domain", "audience", "expected"),
    [
        ("short", 60, "127.0.0.1", True, "example.cloudflareaccess.com", "aud", "secretKey"),
        ("x" * 32, 120, "127.0.0.1", True, "example.cloudflareaccess.com", "aud", "tokenExpireMinutes"),
        ("x" * 32, 60, "0.0.0.0", True, "example.cloudflareaccess.com", "aud", "localhost origin"),
        ("x" * 32, 60, "127.0.0.1", False, "example.cloudflareaccess.com", "aud", "secure session cookie"),
        ("x" * 32, 60, "127.0.0.1", True, "", "aud", "cloudflareAccessTeamDomain"),
        ("x" * 32, 60, "127.0.0.1", True, "example.cloudflareaccess.com", "", "cloudflareAccessAudience"),
    ],
)
def test_validate_console_security_rejects_unsafe_public_dev(
    secret_key,
    expire_minutes,
    host,
    cookie_secure,
    team_domain,
    audience,
    expected,
):
    cfg = SimpleNamespace(
        public_dev=True,
        secret_key=secret_key,
        token_expire_minutes=expire_minutes,
        session_cookie_secure=cookie_secure,
        cloudflare_access_team_domain=team_domain,
        cloudflare_access_audience=audience,
    )

    with pytest.raises(RuntimeError, match=expected):
        validate_console_security(cfg, host)


def test_validate_console_security_accepts_safe_public_dev():
    cfg = SimpleNamespace(
        public_dev=True,
        secret_key="x" * 48,
        token_expire_minutes=60,
        session_cookie_secure=True,
        cloudflare_access_team_domain="example.cloudflareaccess.com",
        cloudflare_access_audience="test-audience",
    )

    validate_console_security(cfg, "127.0.0.1")
