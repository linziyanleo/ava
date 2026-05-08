from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def assert_contains_all(source: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in source]
    assert missing == []


def test_electron_main_starts_healthchecks_and_stops_ava_core() -> None:
    main = read("electron/main.mjs")
    wrapper = read("electron/bin/ava-core")

    assert_contains_all(
        main,
        [
            "spawn('/bin/bash', [wrapper]",
            "AVA_DESKTOP: '1'",
            "CAFE_CONSOLE_HOST: config.host",
            "CAFE_CONSOLE_PORT: String(config.port)",
            "waitForAvaCore(config.healthEndpoint)",
            "/api/gateway/health",
            "mainWindow.loadURL(config.coreEndpoint)",
            "child.kill('SIGTERM')",
            "child.kill('SIGKILL')",
            "contextIsolation: true",
            "nodeIntegration: false",
            "sandbox: true",
        ],
    )
    assert_contains_all(wrapper, ["scripts/start-ava.sh gateway", "trap shutdown INT TERM", "wait \"${core_pid}\""])


def test_preload_exposes_only_p1b_native_whitelist() -> None:
    preload = read("electron/preload.cjs")
    assert_contains_all(
        preload,
        [
            "contextBridge.exposeInMainWorld('avaDesktop', api)",
            "selectDirectory",
            "openPath",
            "getAppConfig",
            "getCoreEndpoint",
            "getAuthToken",
            "showNotification",
        ],
    )
    assert "require('fs')" not in preload
    assert "nodeIntegration" not in preload


def test_pnpm_build_scripts_and_readme_are_present() -> None:
    root_package = json.loads(read("package.json"))
    electron_package = json.loads(read("electron/package.json"))
    build_script = read("electron/scripts/build.mjs")
    readme = read("electron/README.md")

    assert root_package["scripts"]["electron:build"] == "pnpm --dir electron build"
    assert root_package["scripts"]["electron:dry-run"] == "pnpm --dir electron build -- --dry-run"
    assert electron_package["main"] == "main.mjs"
    assert electron_package["scripts"]["build"] == "node scripts/build.mjs"
    assert_contains_all(
        build_script,
        [
            "const dryRun = process.argv.includes('--dry-run')",
            "AVA Electron dry-run passed",
            "npm', ['run', 'build']",
            "electron-packager",
            "--platform=darwin",
            "--arch=arm64",
        ],
    )
    assert_contains_all(readme, ["pnpm electron:build", "pnpm electron:dry-run", "open electron/dist/Ava-darwin-arm64/Ava.app"])


def test_electron_dry_run_build_script_executes() -> None:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [node, "electron/scripts/build.mjs", "--dry-run"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "AVA Electron dry-run passed" in result.stdout
