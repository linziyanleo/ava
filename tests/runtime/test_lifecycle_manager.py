"""LifecycleManager 测试。"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ava.runtime.lifecycle import LifecycleManager, _detect_supervisor
from ava.runtime.paths import get_pid_file


class TestLifecycleManagerInit:
    def test_initialize_writes_state(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()

        state_file = tmp_path / "state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["pid"] == os.getpid()
        assert state["boot_generation"] == 1
        assert state["entry_point"] == "python -m ava gateway"

    def test_boot_generation_increments(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"boot_generation": 3, "pid": 1}))

        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()

        assert mgr.boot_generation == 4
        new_state = json.loads(state_file.read_text())
        assert new_state["boot_generation"] == 4

    def test_first_boot_generation_is_1(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()
        assert mgr.boot_generation == 1

    def test_creates_runtime_dir(self, tmp_path):
        runtime = tmp_path / "nested" / "runtime"
        mgr = LifecycleManager(runtime_dir=runtime)
        mgr.initialize()
        assert runtime.exists()


class TestSupervisorDetection:
    def test_explicit_docker(self):
        with patch.dict(os.environ, {"AVA_SUPERVISOR": "docker"}):
            supervised, kind = _detect_supervisor()
            assert supervised is True
            assert kind == "docker"

    def test_explicit_systemd(self):
        with patch.dict(os.environ, {"AVA_SUPERVISOR": "systemd"}):
            supervised, kind = _detect_supervisor()
            assert supervised is True
            assert kind == "systemd"

    def test_explicit_none(self):
        with patch.dict(os.environ, {"AVA_SUPERVISOR": "none"}):
            supervised, kind = _detect_supervisor()
            assert supervised is False
            assert kind == "none"

    def test_default_unsupervised(self):
        env = {k: v for k, v in os.environ.items() if k != "AVA_SUPERVISOR"}
        env.pop("INVOCATION_ID", None)
        with patch.dict(os.environ, env, clear=True):
            supervised, kind = _detect_supervisor()
            assert supervised is False
            assert kind == "none"

    def test_systemd_via_invocation_id(self):
        env = {k: v for k, v in os.environ.items() if k != "AVA_SUPERVISOR"}
        env["INVOCATION_ID"] = "abc123"
        with patch.dict(os.environ, env, clear=True):
            supervised, kind = _detect_supervisor()
            assert supervised is True
            assert kind == "systemd"


class TestGetStatus:
    def test_returns_lifecycle_fields(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path, gateway_port=18790, console_port=6688)
        mgr.initialize()

        status = mgr.get_status()
        assert status["running"] is True
        assert status["pid"] == os.getpid()
        assert status["boot_generation"] >= 1
        assert "supervised" in status
        assert "restart_pending" in status

    def test_is_healthy_returns_ready(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()

        health = mgr.is_healthy()
        assert health["ready"] is True
        assert health["shutting_down"] is False


class TestRestartRequest:
    def test_unsupervised_rejects_restart(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.supervised = False
        mgr.supervisor = "none"

        result = mgr.request_restart(requested_by="console")
        assert result["status"] == "rejected"
        assert "unsupervised" in result["message"]

    def test_supervised_accepts_restart(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()
        mgr.supervised = True
        mgr.supervisor = "docker"

        with patch("os.kill") as mock_kill:
            result = mgr.request_restart(
                requested_by="console:admin",
                reason="test restart",
            )

        assert result["status"] == "accepted"
        req_file = tmp_path / "restart_request.json"
        assert req_file.exists()
        req = json.loads(req_file.read_text())
        assert req["requested_by"] == "console:admin"
        assert req["reason"] == "test restart"

    def test_restart_request_includes_task_id(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()
        mgr.supervised = True
        mgr.supervisor = "docker"

        with patch("os.kill"):
            mgr.request_restart(
                requested_by="console:admin",
                task_id="abc123",
                origin_session_key="console:session_xyz",
                reason="code changes",
            )

        req = json.loads((tmp_path / "restart_request.json").read_text())
        assert req["task_id"] == "abc123"
        assert req["origin_session_key"] == "console:session_xyz"


class TestPendingRestart:
    def test_check_pending_returns_none_when_empty(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        assert mgr.check_pending_restart() is None

    def test_check_pending_reads_request(self, tmp_path):
        req_file = tmp_path / "restart_request.json"
        req_file.write_text(json.dumps({"requested_by": "console", "reason": "test"}))

        mgr = LifecycleManager(runtime_dir=tmp_path)
        pending = mgr.check_pending_restart()
        assert pending is not None
        assert pending["requested_by"] == "console"

    def test_initialize_clears_pending_request(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"boot_generation": 1, "pid": 1}))
        req_file = tmp_path / "restart_request.json"
        req_file.write_text(json.dumps({"requested_by": "console"}))

        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()

        assert not req_file.exists()
        assert mgr.boot_generation == 2


class TestOrphanRecovery:
    def test_recover_with_bg_store(self, tmp_path):
        mock_store = MagicMock()
        mock_store.recover_orphan_tasks.return_value = 3

        mgr = LifecycleManager(runtime_dir=tmp_path, bg_store=mock_store)
        mgr.initialize()

        mock_store.recover_orphan_tasks.assert_called_once_with(mgr.boot_generation)

    def test_no_recovery_without_store(self, tmp_path):
        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.initialize()


class TestCleanup:
    def test_cleanup_removes_pid_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AVA_HOME", str(tmp_path / "ava-home"))
        pid_file = get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("12345")

        mgr = LifecycleManager(runtime_dir=tmp_path)
        mgr.cleanup()

        assert not pid_file.exists()
