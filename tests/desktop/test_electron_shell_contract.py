from __future__ import annotations

import json
import os
import socket
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def assert_contains_all(source: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in source]
    assert missing == []


def test_electron_main_starts_healthchecks_and_stops_ava_core() -> None:
    main = read("electron/main.mjs")
    wrapper = read("electron/bin/ava-core")
    core_health = read("electron/lib/core-health.mjs")
    desktop_config = read("electron/lib/desktop-config.mjs")
    launch_env = read("electron/lib/launch-env.mjs")
    runtime_manifest = read("electron/lib/runtime-manifest.mjs")

    assert_contains_all(
        main,
        [
            "app.requestSingleInstanceLock()",
            "async function createLaunchConfig()",
            "import { pickFreePort } from './lib/ports.mjs'",
            "from './lib/launch-env.mjs'",
            "from './lib/runtime-manifest.mjs'",
            "resolveExistingAvaCore",
            "readRuntimeManifestRepoRoot(runtimeManifestPaths(__dirname))",
            "const existingCore = await resolveExistingAvaCore(host, preferredPort);",
            "readStoredDesktopConfig(app.getPath('appData'))",
            "resolveStoredNanobotCandidate({",
            "saveNanobotRoot(app.getPath('appData'), root)",
            "validateNanobotRoot(nanobotRoot)",
            "return null;",
            "spawn('/bin/bash', [wrapper]",
            "waitForAvaCoreOrExit(child, config)",
            "/api/gateway/health",
            "mainWindow.loadURL(config.coreEndpoint)",
            "child.kill('SIGTERM')",
            "child.kill('SIGKILL')",
            "stdio: ['ignore', 'pipe', 'pipe']",
            "path.join(os.homedir(), 'Library', 'Logs', 'Ava')",
            "Menu.setApplicationMenu(menu)",
            "label: 'Edit'",
            "label: 'View'",
            "label: 'Window'",
            "label: 'Retry Core'",
            "role: 'toggleDevTools'",
            "if (process.platform !== 'darwin') {\n    app.quit();\n  }",
            "app.on('activate', () => {",
            "showMainWindow().catch(showFatalStartupError)",
            "ipcMain.handle('ava:getBootstrapState'",
            "mainWindow?.webContents.send('ava:openTaskFloater', { taskId })",
            "parseStructuredStartupError(stderrTail)",
            "const RING_BUFFER_BYTES = 256 * 1024",
            "function appendRingBuffer(buffer, chunk, maxBytes = RING_BUFFER_BYTES)",
            "stderrTail = appendRingBuffer(stderrTail, chunk)",
            "detailParts.join('\\n\\n').slice(0, RING_BUFFER_BYTES)",
            "buttons: ['Retry', 'Pick nanobot', 'Open logs', 'Quit']",
            "function showFatalStartupError(error)",
            "dialog.showErrorBox('Ava startup failed'",
            ".catch(showFatalStartupError)",
            "Log setup also failed:",
            "externalCore",
            "isHealthyCorePayload",
            "startConsoleReadyWatcher(config)",
            "await loadConsole(config, 'startup')",
            "await loadConsole(config, 'existing core')",
            "loading Console from ${config.coreEndpoint}",
            "Ava core is ready",
            "SETUP_LOAD_TIMEOUT_MS",
            "mainWindow.on('closed', () => {\n    clearTimeout(setupLoadTimeout);\n    mainWindow = null;\n  });",
            "did-finish-load",
            "Setup surface did not finish loading.",
            "active.child.kill('SIGKILL')",
            "clearTimeout(killTimeout)",
            "active.child.kill('SIGTERM')",
            "env: resolveLaunchPath(process.env)",
            "contextIsolation: true",
            "nodeIntegration: false",
            "sandbox: true",
        ],
    )
    assert_contains_all(
        core_health,
        [
            "export async function detectExistingAvaCore(host, port",
            "export function isHealthyCorePayload(health)",
            "export function readConsoleMetaCandidate(options = {})",
            "export async function resolveExistingAvaCore(preferredHost, preferredPort",
            "path.join(avaHome, 'console.json')",
            "JSON.parse(fs.readFileSync(metaPath, 'utf8'))",
        ],
    )
    assert_contains_all(wrapper, ["scripts/start-ava.sh gateway", "trap shutdown INT TERM", "wait \"${core_pid}\""])
    assert_contains_all(
        desktop_config,
        [
            "export function readDesktopConfig(appDataPath)",
            "JSON.parse(fs.readFileSync(filePath, 'utf8'))",
            "return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};",
            "export function validateNanobotRoot(root)",
            "nanobot root must be an absolute path",
            "path.join('nanobot', 'cli', 'commands.py')",
            "export function resolveNanobotCandidate({ repoRoot, appDataPath, env = process.env })",
            "export function saveNanobotRoot(appDataPath, root",
        ],
    )
    assert_contains_all(
        launch_env,
        [
            "export function resolveLaunchPath(env = process.env",
            "readLoginShellPath(env, options)",
            "desktopPathDefaults(homeDir)",
            "path.join(homeDir, '.pyenv', 'shims')",
            "path.join(homeDir, '.real', '.bin')",
            "export function findExecutable(command, env)",
            "export function buildCoreEnv(config, nanobotRoot)",
            "AVA_DESKTOP_CONSOLE_PORT: String(config.port)",
        ],
    )
    assert_contains_all(
        runtime_manifest,
        [
            "export const RUNTIME_MANIFEST_NAME = 'ava-runtime-manifest.json'",
            "export function isAvaRepoRoot(root)",
            "export function runtimeManifestPaths(moduleDir",
            "export function readRuntimeManifestRepoRoot(paths)",
            "path.join(path.resolve(root), 'scripts', 'start-ava.sh')",
        ],
    )


def test_electron_port_picker_falls_back_when_preferred_port_is_busy() -> None:
    node = shutil.which("node")
    assert node is not None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        busy_port = server.getsockname()[1]
        result = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                "import { pickFreePort } from './electron/lib/ports.mjs';"
                "const selected = await pickFreePort(Number(process.env.BUSY_PORT));"
                "console.log(String(selected));",
            ],
            cwd=ROOT,
            env={**os.environ, "BUSY_PORT": str(busy_port)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    assert result.returncode == 0, result.stdout
    selected_port = int(result.stdout.strip())
    assert selected_port > 0
    assert selected_port != busy_port


def test_runtime_manifest_module_resolves_repo_root(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    fake_repo = tmp_path / "ava"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "scripts" / "start-ava.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    manifest = tmp_path / "ava-runtime-manifest.json"
    bad_manifest = tmp_path / "bad-runtime-manifest.json"
    manifest.write_text(json.dumps({"repoRoot": str(fake_repo)}), encoding="utf-8")
    bad_manifest.write_text("{", encoding="utf-8")
    script = """
import {
  isAvaRepoRoot,
  readRuntimeManifestRepoRoot,
  runtimeManifestPaths,
} from './electron/lib/runtime-manifest.mjs';

if (!isAvaRepoRoot(process.env.FAKE_REPO)) {
  throw new Error('valid repo root was rejected');
}
if (isAvaRepoRoot(process.env.MISSING_REPO)) {
  throw new Error('missing repo root was accepted');
}
const paths = runtimeManifestPaths('/module/dir', { AVA_RUNTIME_MANIFEST: process.env.MANIFEST });
if (paths[0] !== process.env.MANIFEST) {
  throw new Error(`env manifest did not win: ${JSON.stringify(paths)}`);
}
const resolved = readRuntimeManifestRepoRoot([process.env.BAD_MANIFEST, process.env.MANIFEST]);
if (resolved !== process.env.FAKE_REPO) {
  throw new Error(`manifest repo root was not resolved: ${resolved}`);
}
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_REPO": str(fake_repo),
            "MISSING_REPO": str(tmp_path / "missing"),
            "MANIFEST": str(manifest),
            "BAD_MANIFEST": str(bad_manifest),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_core_health_module_detects_existing_core_and_runtime_meta(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    ava_home = tmp_path / "ava-home"
    script = """
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {
  detectExistingAvaCore,
  isHealthyCorePayload,
  readConsoleMetaCandidate,
  resolveExistingAvaCore,
} from './electron/lib/core-health.mjs';

const servers = [];
async function makeServer(payload) {
  const server = http.createServer((_request, response) => {
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify(payload));
  });
  servers.push(server);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return server.address().port;
}

try {
  if (!isHealthyCorePayload({ ready: true, shutting_down: false, boot_generation: 1 })) {
    throw new Error('healthy payload was rejected');
  }
  if (isHealthyCorePayload({ ready: true, shutting_down: true, boot_generation: 1 })) {
    throw new Error('shutting down payload must be rejected');
  }
  const healthyPort = await makeServer({ ready: true, shutting_down: false, boot_generation: 1 });
  const unhealthyPort = await makeServer({ ready: true, shutting_down: true, boot_generation: 1 });
  if (!await detectExistingAvaCore('127.0.0.1', healthyPort)) {
    throw new Error('healthy core was not detected');
  }
  if (await detectExistingAvaCore('127.0.0.1', unhealthyPort)) {
    throw new Error('shutting down core must not be accepted');
  }

  const avaHome = process.env.AVA_HOME_FIXTURE;
  fs.mkdirSync(avaHome, { recursive: true });
  fs.writeFileSync(path.join(avaHome, 'console.json'), '{', 'utf8');
  if (readConsoleMetaCandidate({ env: { AVA_HOME: avaHome } }) !== null) {
    throw new Error('bad console meta must be ignored');
  }
  fs.writeFileSync(
    path.join(avaHome, 'console.json'),
    JSON.stringify({ console_host: '0.0.0.0', console_port: healthyPort }),
    'utf8',
  );
  const candidate = readConsoleMetaCandidate({ env: { AVA_HOME: avaHome } });
  if (!candidate || candidate.host !== '127.0.0.1' || candidate.port !== healthyPort) {
    throw new Error(`console meta candidate was not normalized: ${JSON.stringify(candidate)}`);
  }
  const resolved = await resolveExistingAvaCore('127.0.0.1', unhealthyPort, {
    env: { AVA_HOME: avaHome },
  });
  if (!resolved || resolved.host !== '127.0.0.1' || resolved.port !== healthyPort) {
    throw new Error(`healthy console meta fallback was not selected: ${JSON.stringify(resolved)}`);
  }
} finally {
  await Promise.all(servers.map((server) => new Promise((resolve) => server.close(resolve))));
}
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env={**os.environ, "AVA_HOME_FIXTURE": str(ava_home)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_launch_env_module_merges_shell_path_and_builds_desktop_env(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_bin = bin_dir / "uv"
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    shell_bin = tmp_path / "fake-shell"
    shell_bin.write_text("#!/bin/sh\nprintf '/shell/bin:/custom/bin\\n'\n", encoding="utf-8")
    shell_bin.chmod(0o755)
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    script = """
import path from 'node:path';
import {
  buildCoreEnv,
  findExecutable,
  resolveLaunchPath,
  splitPath,
} from './electron/lib/launch-env.mjs';

const env = resolveLaunchPath(
  { SHELL: process.env.SHELL_FIXTURE, PATH: `${process.env.BIN_DIR}:/usr/bin:/shell/bin` },
  { homeDir: process.env.FAKE_HOME, timeoutMs: 1000 },
);
const parts = splitPath(env.PATH);
if (parts[0] !== '/shell/bin' || parts[1] !== '/custom/bin') {
  throw new Error(`login shell PATH must win: ${env.PATH}`);
}
if (parts.filter((segment) => segment === '/shell/bin').length !== 1) {
  throw new Error(`PATH segments must be deduplicated: ${env.PATH}`);
}
if (!parts.includes(path.join(process.env.FAKE_HOME, '.pyenv', 'shims'))) {
  throw new Error(`pyenv shims default missing: ${env.PATH}`);
}
if (findExecutable('uv', env) !== path.join(process.env.BIN_DIR, 'uv')) {
  throw new Error('uv executable was not resolved from merged PATH');
}
const coreEnv = buildCoreEnv(
  { env, repoRoot: '/repo/ava', host: '127.0.0.1', port: 6688 },
  '/repo/nanobot',
);
if (coreEnv.AVA_DESKTOP !== '1' || coreEnv.AVA_REPO_ROOT !== '/repo/ava') {
  throw new Error('desktop env flags were not set');
}
if (coreEnv.AVA_NANOBOT_ROOT !== '/repo/nanobot') {
  throw new Error('nanobot root was not propagated');
}
if (coreEnv.AVA_DESKTOP_CONSOLE_PORT !== '6688' || coreEnv.CAFE_CONSOLE_PORT !== '6688') {
  throw new Error('console ports were not propagated');
}
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env={
            **os.environ,
            "BIN_DIR": str(bin_dir),
            "SHELL_FIXTURE": str(shell_bin),
            "FAKE_HOME": str(fake_home),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_desktop_env_overrides_python_configured_console_port() -> None:
    node = shutil.which("node")
    assert node is not None
    script = """
import { buildCoreEnv } from './electron/lib/launch-env.mjs';

const coreEnv = buildCoreEnv(
  { env: process.env, repoRoot: '/repo/ava', host: '127.0.0.1', port: 54321 },
  '/repo/nanobot',
);
console.log(JSON.stringify({
  AVA_DESKTOP: coreEnv.AVA_DESKTOP,
  AVA_DESKTOP_CONSOLE_PORT: coreEnv.AVA_DESKTOP_CONSOLE_PORT,
  CAFE_CONSOLE_PORT: coreEnv.CAFE_CONSOLE_PORT,
}));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env=os.environ,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    desktop_env = json.loads(result.stdout)

    from types import SimpleNamespace

    from ava.patches.console_patch import resolve_console_port

    with patch.dict(os.environ, desktop_env, clear=False):
        assert resolve_console_port(SimpleNamespace(port=6688)) == 54321


def test_desktop_config_module_validates_and_resolves_nanobot_root(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    app_data = tmp_path / "app-data"
    empty_app_data = tmp_path / "empty-app-data"
    repo_root = tmp_path / "repo" / "ava"
    nanobot_root = tmp_path / "nanobot"
    missing_root = tmp_path / "missing"
    for root in [repo_root, nanobot_root / "nanobot" / "cli", missing_root]:
        root.mkdir(parents=True)
    (nanobot_root / "pyproject.toml").write_text("[project]\nname = \"nanobot\"\n", encoding="utf-8")
    (nanobot_root / "nanobot" / "__main__.py").write_text("", encoding="utf-8")
    (nanobot_root / "nanobot" / "cli" / "commands.py").write_text("", encoding="utf-8")
    broken_app_data = tmp_path / "broken-app-data"
    broken_config_dir = broken_app_data / "Ava"
    broken_config_dir.mkdir(parents=True)
    (broken_config_dir / "desktop.json").write_text("{", encoding="utf-8")

    script = """
import {
  readDesktopConfig,
  resolveNanobotCandidate,
  saveNanobotRoot,
  validateNanobotRoot,
} from './electron/lib/desktop-config.mjs';

const appDataPath = process.env.APP_DATA;
const brokenAppDataPath = process.env.BROKEN_APP_DATA;
const emptyAppDataPath = process.env.EMPTY_APP_DATA;
const repoRoot = process.env.REPO_ROOT_FIXTURE;
const nanobotRoot = process.env.NANOBOT_ROOT_FIXTURE;
const missingRoot = process.env.MISSING_ROOT_FIXTURE;

const invalidRelative = validateNanobotRoot('relative');
if (invalidRelative.ok || !invalidRelative.error.includes('absolute path')) {
  throw new Error('relative nanobot root must be rejected');
}
const invalidMissing = validateNanobotRoot(missingRoot);
if (invalidMissing.ok || !invalidMissing.error.includes('pyproject.toml')) {
  throw new Error('incomplete nanobot root must be rejected');
}
const valid = validateNanobotRoot(nanobotRoot);
if (!valid.ok) {
  throw new Error(`valid nanobot root rejected: ${valid.error}`);
}
const saved = saveNanobotRoot(appDataPath, nanobotRoot, '2026-01-01T00:00:00.000Z');
if (!saved.ok || saved.nanobotRoot !== nanobotRoot) {
  throw new Error('nanobot root was not saved');
}
const stored = readDesktopConfig(appDataPath);
if (stored.nanobotRoot !== nanobotRoot || stored.createdAt !== '2026-01-01T00:00:00.000Z') {
  throw new Error('saved desktop config is wrong');
}
if (Object.keys(readDesktopConfig(brokenAppDataPath)).length !== 0) {
  throw new Error('broken desktop config must be ignored');
}
const envCandidate = resolveNanobotCandidate({
  repoRoot,
  appDataPath,
  env: { AVA_NANOBOT_ROOT: missingRoot },
});
if (envCandidate !== missingRoot) {
  throw new Error('AVA_NANOBOT_ROOT must win');
}
const storedCandidate = resolveNanobotCandidate({ repoRoot, appDataPath, env: {} });
if (storedCandidate !== nanobotRoot) {
  throw new Error('stored nanobotRoot must be used');
}
const defaultCandidate = resolveNanobotCandidate({ repoRoot, appDataPath: emptyAppDataPath, env: {} });
if (!defaultCandidate.endsWith('/repo/nanobot')) {
  throw new Error(`default sibling nanobot path is wrong: ${defaultCandidate}`);
}
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env={
            **os.environ,
            "APP_DATA": str(app_data),
            "BROKEN_APP_DATA": str(broken_app_data),
            "EMPTY_APP_DATA": str(empty_app_data),
            "REPO_ROOT_FIXTURE": str(repo_root),
            "NANOBOT_ROOT_FIXTURE": str(nanobot_root),
            "MISSING_ROOT_FIXTURE": str(missing_root),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_preload_exposes_only_p1b_native_whitelist() -> None:
    preload = read("electron/preload.cjs")
    assert_contains_all(
        preload,
        [
            "contextBridge.exposeInMainWorld('avaDesktop', api)",
            "selectDirectory",
            "openPath",
            "openLogs",
            "getAppConfig",
            "getCoreEndpoint",
            "getAuthToken",
            "getBootstrapState",
            "readDesktopConfig",
            "setNanobotRoot",
            "retryCore",
            "cancelBootstrap",
            "onBootstrapState",
            "onOpenTaskFloater",
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
    electron_spec = read(".specanchor/modules/electron.spec.md")

    assert root_package["scripts"]["electron:build"] == "pnpm --dir electron install --frozen-lockfile && pnpm --dir electron build"
    assert root_package["scripts"]["electron:dry-run"] == "pnpm --dir electron install --frozen-lockfile && pnpm --dir electron build -- --dry-run"
    assert electron_package["main"] == "main.mjs"
    assert electron_package["scripts"]["build"] == "node scripts/build.mjs"
    assert_contains_all(
        build_script,
        [
            "const dryRun = process.argv.includes('--dry-run')",
            "AVA Electron dry-run passed",
            "npm', ['run', 'build']",
            "electron-packager",
            "electron/lib/core-health.mjs",
            "electron/lib/desktop-config.mjs",
            "electron/lib/launch-env.mjs",
            "electron/lib/ports.mjs",
            "electron/lib/runtime-manifest.mjs",
            "--platform=darwin",
            "--arch=arm64",
            "const runtimeManifestName = 'ava-runtime-manifest.json'",
            "function writeRuntimeManifest()",
            "--extra-resource=${manifestPath}",
            "invalid runtime manifest repoRoot",
            "function findCachedElectronZipDir(cacheRoot, version",
            "--electron-zip-dir=",
            "--download.cacheRoot",
            "function verifyPackagedApp(appPath)",
            "function readPlistValue(plistPath, key)",
            "CFBundleExecutable",
            "path.join(appPath, 'Contents', 'MacOS', bundleExecutable)",
            "Ava Helper (Renderer).app",
            "codesign",
            "--sign",
            "--verify",
            "--strict",
        ],
    )
    assert_contains_all(
        readme,
        [
            "pnpm electron:build",
            "Root `pnpm electron:build` installs the Electron shell dependencies",
            "pnpm electron:dry-run",
            "../docs/desktop-launch-acceptance.md",
            "not by a bare `open` command",
            "scripts/verify-desktop-handoff-ready.sh",
            "scripts/verify-desktop-handoff-ready.sh --port-conflict",
            "scripts/verify-desktop-closeout-records.sh",
            "selected local core endpoint",
            "Port `6688` is only the preferred starting point",
            "dynamic port",
            "ava-runtime-manifest.json",
            "copy the generated `.app` to `/Applications`",
            "not a copy-to-another-machine distribution package",
        ],
    )
    assert "cd ../electron && pnpm install" not in readme
    assert "open electron/dist/Ava-darwin-arm64/Ava.app" not in readme
    assert "http://127.0.0.1:6688/" not in readme
    assert_contains_all(
        electron_spec,
        [
            "electron/README.md",
            "scripts/verify-desktop-closeout-records.sh",
            "不得恢复 `cd electron && pnpm install` 或 bare `open electron/dist/...`",
            "electron/lib/runtime-manifest.mjs",
            "ava-runtime-manifest.json",
            "Contents/Resources/",
        ],
    )


def test_setup_surface_and_desktop_ipc_contract_are_present() -> None:
    setup_html = read("electron/setup.html")
    settings = read("console-ui/src/pages/SettingsPage.tsx")
    app = read("console-ui/src/App.tsx")

    assert_contains_all(
        setup_html,
        [
            "Ava Setup",
            "onBootstrapState",
            "setNanobotRoot",
            "retryCore",
            "cancelBootstrap",
            "openLogs",
        ],
    )
    assert_contains_all(
        settings,
        [
            "DesktopSettingsPage",
            "readDesktopConfig",
            "setNanobotRoot",
            "Retry Core",
            "Open Logs",
            "Codex Config",
            "/settings/agents-config/codex/config",
            "Claude Code Config",
            "/settings/agents-config/claude-code/config",
        ],
    )
    assert_contains_all(app, ["system/desktop", "DesktopSettingsPage"])


def test_current_feature_inventory_records_desktop_and_hook_boundaries() -> None:
    inventory = read("docs/current-feature-inventory.md")

    assert_contains_all(
        inventory,
        [
            "Login, refresh, current-user, and logout flows are backed by `/api/auth/*`",
            "Settings -> System -> Desktop exposes nanobot checkout selection, retry, logs, and links to Codex / Claude Code config editors",
            "System settings subpages are Desktop, LAN Access, Gateway, Browser, Console, and Version.",
            "Browser system page shows active page-agent sessions with screencast frames, page URL/status, step count, and agent activity events.",
            "`/lan/pair` is the mobile device pairing entry outside the main protected shell.",
            "Chat HUD exposes Token, Skills, Artifacts, and Memory widgets",
            "Chat supports session create/rename/stop/delete/history, context size, compression history, context preview, message queries, uploads, and conversation listing",
            "Direct task submission is exposed through `/api/console/direct-tasks`",
            "TaskPreviewBar shows active background tasks in the global shell; TaskFloater tabs cover background tasks, scheduled tasks, and artifacts.",
            "TaskFloater/Task Overlay can deep-link via `?view=tasks`, `task_view`, `task_id`, `chain_id`, and `trace_id`",
            "Current backend surfaces include `/api/bg-tasks`, `/api/workflows`, `/api/artifacts`, `/api/page-agent`, `/api/media`, `/api/files`, and `/api/audit`",
            "Config pages manage nanobot, console, Codex, Claude Code, and Image Gen config files with list/read/update/reveal operations",
            "Gateway status, health, console rebuild, and restart are exposed under `/api/gateway/*`.",
            "Skills page manages built-in skills, skill detail/toggle/delete/install flows, MCP status/test/reconnect, and tool registry status.",
            "Non-sandbox Finder/LaunchServices and visual setup/cancel/logs acceptance is still tracked in `docs/desktop-launch-acceptance.md`",
            "Current reliable progress source is Ava-owned: `BackgroundTaskStore`",
            "Current display surfaces are Agent Registry active task counts, recent events, recent artifacts, task cancel actions, and TaskFloater background-task views.",
            "Claude Code and Codex native hook/status systems should not be read directly by Electron.",
            "Existing `BackgroundTaskStore` post-task hooks are local completion hooks, currently used for console-ui rebuild checks; they are not native Claude Code or Codex progress ingestion.",
            "Repo code does not yet include a Claude Code/Codex native hook ingestion adapter.",
        ],
    )


def test_desktop_port_and_nanobot_error_contracts_are_present() -> None:
    console_patch = read("ava/patches/console_patch.py")
    start_script = read("scripts/start-ava.sh")

    assert_contains_all(
        console_patch,
        [
            "def resolve_console_port",
            'os.environ.get("AVA_DESKTOP") == "1"',
            'os.environ.get("AVA_DESKTOP_CONSOLE_PORT")',
        ],
    )
    assert_contains_all(
        start_script,
        [
            "json_string()",
            '"error":"nanobot_not_found"',
            "nanobot/cli/commands.py",
        ],
    )


def test_desktop_start_script_emits_structured_nanobot_error(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-nanobot"
    env = os.environ.copy()
    env["AVA_DESKTOP"] = "1"
    env["AVA_NANOBOT_ROOT"] = str(missing_root)

    result = subprocess.run(
        ["bash", "scripts/start-ava.sh", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    first_line = result.stderr.splitlines()[0]
    parsed = json.loads(first_line)
    assert parsed == {
        "error": "nanobot_not_found",
        "path": str(missing_root),
        "message": "nanobot checkout not found",
    }


def test_desktop_launch_verifier_script_contract() -> None:
    verifier = read("scripts/verify-desktop-launch.sh")
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    handoff_ready = read("scripts/verify-desktop-handoff-ready.sh")
    acceptance_doc = read("docs/desktop-launch-acceptance.md")
    assert_contains_all(
        verifier,
        [
            "open -n",
            "codesign --verify --deep --strict --verbose=1",
            "read_plist_value",
            "absolute_app_path",
            "CFBundleExecutable",
            "Contents/MacOS/${BUNDLE_EXECUTABLE}",
            "require_mach_o_executable",
            "Mach-O 64-bit executable",
            "Main executable type:",
            "running_app_pids()",
            "lsof -nP -c \"${bundle_executable}\"",
            "pgrep -f \"${main_executable}\"",
            "Ava.app is already running from ${APP_ABS_PATH} (pid(s):",
            "quit it before running this verifier",
            "could not determine whether Ava.app is already running",
            "pgrep failed and lsof found no matching executable",
            "MAIN_LOG_SIZE",
            "CORE_LOG_SIZE",
            "MAIN_LOG_ID",
            "CORE_LOG_ID",
            "log_identity()",
            '"${current_id}" != "${previous_id}"',
            "current_size < offset",
            "latest_endpoint_from_new_log",
            "fail_on_new_core_errors",
            'log_since "${MAIN_LOG}" "${MAIN_LOG_SIZE}" "${MAIN_LOG_ID}" >&2',
            'log_since "${CORE_LOG}" "${CORE_LOG_SIZE}" "${CORE_LOG_ID}" >&2',
            "coreEndpoint=http://",
            "Gateway crashed unexpectedly",
            "Traceback",
            "/api/gateway/health",
            "payload.get(\"ready\") is True",
            "payload.get(\"shutting_down\") is False",
            "payload.get(\"boot_generation\")",
            "Ava opened but the new core log contains startup errors",
            "LaunchServices open failed",
            "AVA_DESKTOP_VERIFY_REQUIRE_FRESH_CORE",
            "AVA_DESKTOP_VERIFY_FORBID_ENDPOINT_PORT",
            "latest_launch_config_from_new_log",
            "fresh_core_required_but_reused_existing",
            "forbidden_endpoint_port_selected",
            "Ava selected forbidden endpoint port",
            "externalCore=true",
            "fresh core was required, but Ava reused an existing core",
        ],
    )
    result = subprocess.run(
        ["bash", "-n", "scripts/verify-desktop-launch.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert_contains_all(
        acceptance,
        [
            "--skip-build",
            "--with-port-conflict",
            "--evidence-log",
            "ORIGINAL_COMMAND=\"$(printf '%q ' \"$0\" \"$@\")\"",
            "ORIGINAL_COMMAND=\"${ORIGINAL_COMMAND% }\"",
            "Evidence log:",
            "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')",
            "Command: ${ORIGINAL_COMMAND}",
            "App path: ${APP_PATH}",
            "Skip build: ${SKIP_BUILD}",
            "With port conflict: ${WITH_PORT_CONFLICT}",
            "Conflict port: ${PORT_CONFLICT_PORT}",
            "on_exit()",
            "EVIDENCE_LOG_STARTED=0",
            '[[ -n "${EVIDENCE_LOG}" && "${EVIDENCE_LOG_STARTED}" == "1" ]]',
            "Automated desktop acceptance checks failed with exit status",
            "Do not paste this evidence log into Result Records as a successful acceptance run.",
            "run_pre_evidence_step()",
            "require_node_for_build",
            "process.versions.node",
            "Node.js 20.19.0 or newer is required",
            "nvm use 20.19.0",
            "if (( SKIP_BUILD == 0 )); then\n  require_node_for_build",
            "run_pre_evidence_step scripts/verify-desktop-handoff-ready.sh --port-conflict \"${APP_PATH}\"",
            "run_pre_evidence_step scripts/verify-desktop-handoff-ready.sh \"${APP_PATH}\"",
            "EVIDENCE_LOG_STARTED=1",
            "Handoff readiness preflight: passed before evidence logging",
            "pnpm electron:build",
            "codesign --verify --deep --strict --verbose=1",
            "scripts/verify-desktop-setup-surface.sh",
            "node scripts/verify-desktop-setup-dom.mjs",
            "scripts/verify-desktop-launch.sh",
            "env AVA_DESKTOP_VERIFY_REQUIRE_FRESH_CORE=1 AVA_DESKTOP_VERIFY_FORBID_ENDPOINT_PORT=\"${PORT_CONFLICT_PORT}\" scripts/verify-desktop-launch.sh",
            "fail_if_runtime_meta_has_healthy_core",
            "fail_if_conflict_port_has_healthy_core",
            "already hosts a healthy Ava core; stop that core before running --with-port-conflict",
            "runtime metadata points to an existing healthy Ava core",
            "validate_closeout_handoff_command",
            "Closeout evidence log ${requested_evidence_log} must be generated with exact command:",
            "urllib.request.urlopen",
            "PORT_CONFLICT_MARKER",
            '"${BASH_SOURCE[0]}" != "$0"',
            "AVA_DESKTOP_VERIFY_ALLOW_CONFLICT_PORT_OVERRIDE",
            "AVA_DESKTOP_VERIFY_CONFLICT_PORT",
            "ava-port-conflict.txt",
            "--directory \"${PORT_CONFLICT_DIR}\"",
            "python3 -m http.server \"${PORT_CONFLICT_PORT}\" --bind 127.0.0.1",
            "127.0.0.1:${PORT_CONFLICT_PORT} is occupied by temporary non-Ava server",
            "Finder double-click Ava.app",
            "Help -> Open Logs",
            "dynamic_port_result=\"not run by this command\"",
            "conflict_port_result=\"not run by this command\"",
            "dynamic_port_result=\"automated --with-port-conflict verifier passed; fresh core required and endpoint port != ${PORT_CONFLICT_PORT}\"",
            "conflict_port_result=\"${PORT_CONFLICT_PORT}\"",
            "evidence_log_value=\"${EVIDENCE_LOG:-not requested}\"",
            "record_date=\"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\"",
            "Acceptance record fields:",
            "Full desktop acceptance is not complete until the manual visual fields below are filled.",
            "Before running the port-conflict handoff, quit the Ava.app instance opened by the previous handoff and make sure 127.0.0.1:${PORT_CONFLICT_PORT} is free",
            "scripts/verify-desktop-handoff-ready.sh --port-conflict",
            "Date: ${record_date}",
            "Command: ${ORIGINAL_COMMAND}",
            "Evidence log: ${evidence_log_value}",
            "Conflict port: ${conflict_port_result}",
            "Console happy path: automated LaunchServices verifier passed",
            "Dynamic-port path: ${dynamic_port_result}",
            "Paste-ready result record:",
            "\\`\\`\\`text",
            "Record these fields in docs/desktop-launch-acceptance.md",
        ],
    )
    result = subprocess.run(
        ["bash", "-n", "scripts/verify-desktop-acceptance.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert_contains_all(
        handoff_ready,
        [
            "Node.js 20.19.0 or newer is required",
            "Usage:",
            "--help|-h",
            "unknown option:",
            "only one app-path may be provided",
            "MODE=\"happy\"",
            "--port-conflict",
            "AVA_DESKTOP_HANDOFF_ALLOW_CONFLICT_PORT_OVERRIDE",
            "healthy_core_at_port",
            "healthy_core_from_runtime_meta",
            "lsof -nP -iTCP:\"${CONFLICT_PORT}\" -sTCP:LISTEN",
            "lsof -nP -p \"${pid}\"",
            "running_app_pids()",
            "lsof -nP -c \"${bundle_executable}\"",
            "pgrep -f \"${main_executable}\"",
            "could not determine whether Ava.app is already running",
            "pgrep failed and lsof found no matching executable",
            "Current listener on 127.0.0.1:${CONFLICT_PORT}:",
            "Listener process cwd:",
            "Listener process executable:",
            "Use the listener row above to identify the owning process",
            "If no original app or terminal is available, use normal SIGTERM: kill ${pid}",
            "print_listener_remediation \"that Ava/core process\" \"${listener}\"",
            "print_listener_remediation \"that process\" \"${listener}\"",
            "print_running_app_remediation()",
            "Ava.app is already running",
            "pid(s): ${running_pids//$'\\n'/, }",
            "Quit the running Ava.app from Dock/Finder",
            "If no app UI is available, use normal SIGTERM: kill ${pid}",
            "port-conflict-only checks skipped for happy-path handoff",
            "app bundle is missing: ${APP_PATH}; run the happy-path evidence command first",
            "already hosts a healthy Ava core",
            "Desktop handoff preflight passed",
            "never writes evidence logs",
            "After fixing blockers, rerun: scripts/verify-desktop-handoff-ready.sh",
            "After fixing blockers, rerun: scripts/verify-desktop-handoff-ready.sh --port-conflict",
            "scripts/verify-desktop-handoff-ready.sh --port-conflict",
            "scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log",
            "scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log",
        ],
    )
    result = subprocess.run(
        ["bash", "-n", "scripts/verify-desktop-handoff-ready.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    help_result = subprocess.run(
        ["scripts/verify-desktop-handoff-ready.sh", "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stdout
    assert "Usage:" in help_result.stdout
    assert "This non-canonical preflight never writes evidence logs." in help_result.stdout
    bad_option = subprocess.run(
        ["scripts/verify-desktop-handoff-ready.sh", "--bogus"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert bad_option.returncode == 2, bad_option.stdout
    assert "unknown option: --bogus" in bad_option.stdout
    assert_contains_all(
        acceptance_doc,
        [
            "scripts/verify-desktop-handoff-ready.sh",
            "scripts/verify-desktop-handoff-ready.sh --port-conflict",
            "The optional readiness preflight below is non-canonical and never writes evidence logs.",
            "The default mode checks the happy-path handoff blockers only",
            "run `--port-conflict` after quitting the first `Ava.app` instance",
            "If either preflight reports an already-running `Ava.app`, quit that app from Dock/Finder first.",
            "If no app UI is available, use normal SIGTERM with the printed PID",
            "If the preflight says it is a healthy Ava core, stop that Ava/core process",
            "otherwise stop the owning process shown by `lsof`",
            "use normal SIGTERM with `kill <PID>` from the `lsof` row",
            "avoid `kill -9` unless SIGTERM fails",
            "Optional readiness preflight:",
            "Default mode checks Node.js `20.19.0+` and the target `Ava.app` process",
            "`--port-conflict` additionally requires `127.0.0.1:6688` to be free",
            "scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log",
            "scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log",
            "To capture closeout evidence, use the exact two-command handoff below.",
            "Run them from the repo root after `nvm use 20.19.0`, in this order",
            "the second command intentionally reuses the app bundle built and signed by the first command",
            "After the first command passes, quit the `Ava.app` instance it opened before running the second command",
            "fails fast unless the command line exactly matches the corresponding command below",
            "Any `docs/desktop-acceptance-*` evidence path that is not one of the two canonical paths below is rejected",
            "fails fast before build if the active shell is not on Node.js `20.19.0` or newer",
            "Optional channel/MCP startup errors do not replace the strict `coreEndpoint` + health check.",
            "Full automated evidence run:",
            "Dynamic-port evidence run:",
            "## Result Records",
            "Canonical automated evidence logs have been generated, but the human visual confirmation fields below are still blank.",
            "Each successful acceptance run prints a `Paste-ready result record` block",
            "The `Command` field must exactly match the corresponding handoff command",
            "The human visual confirmation fields must match exactly between this document and the active Task Spec.",
            "Do not use any evidence log containing `Automated desktop acceptance checks failed` as a successful Result Record.",
            "Do not treat `Automated desktop acceptance checks passed` alone as full acceptance",
            "mirror the same result summary in the active Task Spec",
            "The full dynamic-port acceptance evidence must use",
            "it does not replace the runner because it lacks the controlled marker file, fresh-core guard, and evidence log",
            "Conflict port:",
        ],
    )
    assert "docs/desktop-acceptance-result.log" not in acceptance_doc


def test_desktop_handoff_ready_preflight_reports_blockers_without_evidence_logs(tmp_path: Path) -> None:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ready": True,
                "shutting_down": False,
                "boot_generation": 1,
            }).encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_node = bin_dir / "node"
    fake_node.write_text(
        """#!/bin/sh
case "$1" in
  -p)
    printf '%s\\n' "20.19.0"
    exit 0
    ;;
  -e)
    exit 0
    ;;
esac
exit 1
""",
        encoding="utf-8",
    )
    fake_node.chmod(0o755)
    ava_home = tmp_path / "ava-home"
    ava_home.mkdir()
    missing_app = tmp_path / "Missing.app"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "AVA_HOME": str(ava_home),
        "AVA_DESKTOP_HANDOFF_ALLOW_CONFLICT_PORT_OVERRIDE": "1",
        "AVA_DESKTOP_HANDOFF_CONFLICT_PORT": str(free_port),
    }
    happy_success = subprocess.run(
        ["scripts/verify-desktop-handoff-ready.sh", str(missing_app)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert happy_success.returncode == 0, happy_success.stdout
    assert "Desktop handoff preflight passed" in happy_success.stdout
    assert "port-conflict-only checks skipped for happy-path handoff" in happy_success.stdout
    assert "evidence log" not in "\n".join(path.name for path in tmp_path.iterdir())

    missing_port_conflict_app = subprocess.run(
        ["scripts/verify-desktop-handoff-ready.sh", "--port-conflict", str(missing_app)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert missing_port_conflict_app.returncode == 1, missing_port_conflict_app.stdout
    assert "app bundle is missing" in missing_port_conflict_app.stdout

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        blocked = subprocess.run(
            ["scripts/verify-desktop-handoff-ready.sh", "--port-conflict", str(missing_app)],
            cwd=ROOT,
            env={**env, "AVA_DESKTOP_HANDOFF_CONFLICT_PORT": str(port)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert blocked.returncode == 1, blocked.stdout
    assert f"Current listener on 127.0.0.1:{port}:" in blocked.stdout
    assert f"127.0.0.1:{port} already hosts a healthy Ava core" in blocked.stdout
    assert "Use the listener row above to identify the owning process" in blocked.stdout
    assert "stop that Ava/core process" in blocked.stdout
    assert "use normal SIGTERM: kill" in blocked.stdout
    assert "After fixing blockers, rerun: scripts/verify-desktop-handoff-ready.sh --port-conflict" in blocked.stdout
    assert "Fix them before generating canonical evidence logs" in blocked.stdout


def test_desktop_acceptance_closeout_handoff_command_is_fail_fast(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    (tmp_path / "docs").mkdir()

    bad_happy = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG="docs/desktop-acceptance-happy.log"
SKIP_BUILD=0
WITH_PORT_CONFLICT=0
ORIGINAL_COMMAND="./scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log"
validate_closeout_handoff_command
""",
        ],
        cwd=tmp_path,
        env={**os.environ, "FUNCTIONS_FILE": str(functions_file)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert bad_happy.returncode == 1
    assert "must be generated with exact command" in bad_happy.stdout
    assert "scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log" in bad_happy.stdout
    assert not (tmp_path / "docs/desktop-acceptance-happy.log").exists()

    bad_closeout_path = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG="docs/desktop-acceptance-port-"
SKIP_BUILD=1
WITH_PORT_CONFLICT=1
ORIGINAL_COMMAND="scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-"
validate_closeout_handoff_command
""",
        ],
        cwd=tmp_path,
        env={**os.environ, "FUNCTIONS_FILE": str(functions_file)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert bad_closeout_path.returncode == 1
    assert "must use one of" in bad_closeout_path.stdout
    assert "docs/desktop-acceptance-port-conflict.log" in bad_closeout_path.stdout
    assert not (tmp_path / "docs/desktop-acceptance-port-").exists()

    good_port = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG="docs/desktop-acceptance-port-conflict.log"
SKIP_BUILD=1
WITH_PORT_CONFLICT=1
ORIGINAL_COMMAND="scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log"
validate_closeout_handoff_command
""",
        ],
        cwd=ROOT,
        env={**os.environ, "FUNCTIONS_FILE": str(functions_file)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert good_port.returncode == 0, good_port.stdout


def test_desktop_acceptance_node_version_preflight(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_node = bin_dir / "node"
    fake_node.write_text(
        """#!/bin/sh
case "$1" in
  -p)
    printf '%s\\n' "${FAKE_NODE_VERSION}"
    exit 0
    ;;
  -e)
    case "${FAKE_NODE_VERSION}" in
      20.19.*|20.2[0-9].*|2[1-9].*) exit 0 ;;
      *) exit 1 ;;
    esac
    ;;
esac
exit 1
""",
        encoding="utf-8",
    )
    fake_node.chmod(0o755)
    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG=""
require_node_for_build
"""

    old_node = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_NODE_VERSION": "20.18.1",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert old_node.returncode == 1, old_node.stdout
    assert "Node.js 20.19.0 or newer is required" in old_node.stdout
    assert "current Node is 20.18.1" in old_node.stdout

    current_node = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_NODE_VERSION": "20.19.0",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert current_node.returncode == 0, current_node.stdout


def test_desktop_acceptance_failed_evidence_log_is_marked(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    evidence_log = tmp_path / "failed-acceptance.log"
    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG="${EVIDENCE_LOG_FIXTURE}"
EVIDENCE_LOG_STARTED=1
emit "before forced failure"
false
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "EVIDENCE_LOG_FIXTURE": str(evidence_log),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1, result.stdout
    log = evidence_log.read_text(encoding="utf-8")
    assert "before forced failure" in log
    assert "Automated desktop acceptance checks failed with exit status 1." in log
    assert "Do not paste this evidence log into Result Records as a successful acceptance run." in log


def test_desktop_acceptance_pre_evidence_failure_preserves_log(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    evidence_log = tmp_path / "existing-acceptance.log"
    evidence_log.write_text("KEEP\n", encoding="utf-8")
    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG="${EVIDENCE_LOG_FIXTURE}"
false
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "EVIDENCE_LOG_FIXTURE": str(evidence_log),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1, result.stdout
    assert evidence_log.read_text(encoding="utf-8") == "KEEP\n"


def test_desktop_acceptance_closeout_logs_are_not_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "docs/desktop-acceptance-happy.log",
            "docs/desktop-acceptance-port-conflict.log",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1, result.stdout


def test_desktop_closeout_records_verifier_contract(tmp_path: Path) -> None:
    verifier = read("scripts/verify-desktop-closeout-records.sh")
    acceptance_doc = read("docs/desktop-launch-acceptance.md")
    task_spec = read(".specanchor/tasks/_cross-module/2026-05-12_electron-headless-launch.spec.md")
    scripts_spec = read(".specanchor/modules/scripts.spec.md")
    assert_contains_all(
        verifier,
        [
            "docs/desktop-acceptance-happy.log",
            "docs/desktop-acceptance-port-conflict.log",
            "def expected_command",
            "Command: {command}",
            "Automated desktop acceptance checks passed.",
            "Automated desktop acceptance checks failed",
            "Paste-ready result record:",
            "def section_after",
            "def require_log_field",
            "def require_matching_human_fields",
            "differs between acceptance doc and task spec",
            "app_path=happy_app_path",
            "## Result Records",
            "## 8. Objective Completion Audit",
            "No non-sandbox desktop acceptance result has been recorded yet.",
            "Partially verified:",
            "### 8.2 Unclosed Acceptance",
            "Do not mark this goal complete yet",
            "Finder double-click, no Terminal",
            "Setup surface visible before Console",
            "Cancel stops uv sync, Retry starts again",
            "Help -> Open Logs opens ~/Library/Logs/Ava",
            "Desktop closeout records verified",
        ],
    )
    assert "scripts/verify-desktop-closeout-records.sh" in acceptance_doc
    assert "scripts/verify-desktop-closeout-records.sh" in task_spec
    assert_contains_all(
        scripts_spec,
        [
            "scripts/verify-desktop-closeout-records.sh",
            "successful evidence log",
            "`Command` 字段精确匹配",
            "人工视觉字段已填",
            "两处内容一致",
            "最终关闭 guard",
        ],
    )

    syntax = subprocess.run(
        ["bash", "-n", "scripts/verify-desktop-closeout-records.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout

    missing_happy = tmp_path / "missing-happy.log"
    missing_port = tmp_path / "missing-port.log"
    result = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(missing_happy),
            str(missing_port),
            "docs/desktop-launch-acceptance.md",
            ".specanchor/tasks/_cross-module/2026-05-12_electron-headless-launch.spec.md",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert f"happy-path evidence log is missing: {missing_happy}" in result.stdout


def test_desktop_closeout_records_verifier_rejects_bad_records(tmp_path: Path) -> None:
    happy_log = tmp_path / "desktop-acceptance-happy.log"
    port_log = tmp_path / "desktop-acceptance-port-conflict.log"
    doc = tmp_path / "desktop-launch-acceptance.md"
    task = tmp_path / "task.spec.md"

    def expected_command(path: Path, *, with_port_conflict: bool) -> str:
        if with_port_conflict:
            return f"scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log {path}"
        return f"scripts/verify-desktop-acceptance.sh --evidence-log {path}"

    def success_log(path: Path, *, with_port_conflict: bool) -> str:
        command = expected_command(path, with_port_conflict=with_port_conflict)
        conflict_port = "6688" if with_port_conflict else "not run by this command"
        skip_build = "1" if with_port_conflict else "0"
        with_conflict = "1" if with_port_conflict else "0"
        dynamic_port = (
            "automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688"
            if with_port_conflict
            else "not run by this command"
        )
        marker = "127.0.0.1:6688 is occupied by temporary non-Ava server\n" if with_port_conflict else ""
        return f"""Evidence log: {path}
Date: 2026-05-13T00:00:00Z
Command: {command}
App path: /tmp/Ava.app
Skip build: {skip_build}
With port conflict: {with_conflict}
Conflict port: {conflict_port}
{marker}
Automated desktop acceptance checks passed.
Paste-ready result record:
```text
Date: 2026-05-13T00:00:00Z
Command: {command}
App path: /tmp/Ava.app
Evidence log: {path}
Conflict port: {conflict_port}
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: {dynamic_port}
Finder double-click, no Terminal:
Setup surface visible before Console:
Cancel stops uv sync, Retry starts again:
Help -> Open Logs opens ~/Library/Logs/Ava:
Notes / log excerpts:
```
"""

    def record(path: Path, *, with_port_conflict: bool, filled: bool = True) -> str:
        command = expected_command(path, with_port_conflict=with_port_conflict)
        conflict_port = "6688" if with_port_conflict else "not run by this command"
        dynamic_port = (
            "automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688"
            if with_port_conflict
            else "not run by this command"
        )
        finder_value = "Confirmed no Terminal window opened" if filled else ""
        return f"""Date: 2026-05-13T00:00:00Z
Command: {command}
App path: /tmp/Ava.app
Evidence log: {path}
Conflict port: {conflict_port}
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: {dynamic_port}
Finder double-click, no Terminal: {finder_value}
Setup surface visible before Console: Confirmed
Cancel stops uv sync, Retry starts again: Confirmed
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed
Notes / log excerpts:
"""

    def task_doc(text: str) -> str:
        return f"## 8. Objective Completion Audit\n\n{text}"

    happy_log.write_text(success_log(happy_log, with_port_conflict=False), encoding="utf-8")
    port_log.write_text(success_log(port_log, with_port_conflict=True), encoding="utf-8")

    doc.write_text(
        f"""## Result Records

{record(happy_log, with_port_conflict=False, filled=False)}
{record(port_log, with_port_conflict=True)}
""",
        encoding="utf-8",
    )
    task.write_text(task_doc(doc.read_text(encoding="utf-8")), encoding="utf-8")

    unfilled = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert unfilled.returncode == 1
    assert "has an unfilled field: Finder double-click, no Terminal" in unfilled.stdout

    happy_log.write_text(
        success_log(happy_log, with_port_conflict=False)
        + "\nAutomated desktop acceptance checks failed with exit status 1.\n",
        encoding="utf-8",
    )
    doc.write_text(
        f"""## Result Records

{record(happy_log, with_port_conflict=False)}
{record(port_log, with_port_conflict=True)}
""",
        encoding="utf-8",
    )
    task.write_text(task_doc(doc.read_text(encoding="utf-8")), encoding="utf-8")

    failed_log = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert failed_log.returncode == 1
    assert "contains forbidden text: Automated desktop acceptance checks failed" in failed_log.stdout

    happy_log.write_text(success_log(happy_log, with_port_conflict=False), encoding="utf-8")
    task.write_text(
        task_doc(doc.read_text(encoding="utf-8"))
        + "\n### 8.3 Completion Decision\n- Do not mark this goal complete yet: still pending.\n",
        encoding="utf-8",
    )
    pending_decision = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert pending_decision.returncode == 1
    assert "contains forbidden text: Do not mark this goal complete yet" in pending_decision.stdout

    task.write_text(
        task_doc(doc.read_text(encoding="utf-8"))
        + "\n### 8.2 Unclosed Acceptance\n- [ ] stale pending gate\n",
        encoding="utf-8",
    )
    unclosed_section = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert unclosed_section.returncode == 1
    assert "contains forbidden text: ### 8.2 Unclosed Acceptance" in unclosed_section.stdout

    task.write_text(task_doc(doc.read_text(encoding="utf-8")), encoding="utf-8")
    success = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert success.returncode == 0, success.stdout
    assert "Desktop closeout records verified" in success.stdout

    mismatched_app_path = doc.read_text(encoding="utf-8").replace("App path: /tmp/Ava.app", "App path: /tmp/Other.app", 1)
    doc.write_text(mismatched_app_path, encoding="utf-8")
    task.write_text(task_doc(mismatched_app_path), encoding="utf-8")
    app_path_mismatch = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert app_path_mismatch.returncode == 1
    assert "field 'App path' expected '/tmp/Ava.app', got '/tmp/Other.app'" in app_path_mismatch.stdout

    valid_records = f"""## Result Records

{record(happy_log, with_port_conflict=False)}
{record(port_log, with_port_conflict=True)}
"""
    doc.write_text(valid_records, encoding="utf-8")
    task.write_text(
        task_doc(
            valid_records.replace(
                "Finder double-click, no Terminal: Confirmed no Terminal window opened",
                "Finder double-click, no Terminal: Confirmed via Task Spec only",
                1,
            )
        ),
        encoding="utf-8",
    )
    human_field_mismatch = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert human_field_mismatch.returncode == 1
    assert "differs between acceptance doc and task spec" in human_field_mismatch.stdout

    doc.write_text(
        f"""## Wrong Section

{record(happy_log, with_port_conflict=False)}
{record(port_log, with_port_conflict=True)}

## Result Records
""",
        encoding="utf-8",
    )
    task.write_text(
        f"""## Wrong Section

{record(happy_log, with_port_conflict=False)}
{record(port_log, with_port_conflict=True)}

## 8. Objective Completion Audit
""",
        encoding="utf-8",
    )
    wrong_section = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert wrong_section.returncode == 1
    assert f"{doc} does not contain a result record for {happy_log}" in wrong_section.stdout


def test_desktop_closeout_records_verifier_accepts_acceptance_runner_output(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    happy_log = tmp_path / "desktop-acceptance-happy.log"
    port_log = tmp_path / "desktop-acceptance-port-conflict.log"
    doc = tmp_path / "desktop-launch-acceptance.md"
    task = tmp_path / "task.spec.md"

    def expected_command(path: Path, *, with_port_conflict: bool) -> str:
        if with_port_conflict:
            return f"scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log {path}"
        return f"scripts/verify-desktop-acceptance.sh --evidence-log {path}"

    def generate_log(path: Path, *, with_port_conflict: bool) -> None:
        script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
WITH_PORT_CONFLICT="${WITH_PORT_CONFLICT_FIXTURE}"
PORT_CONFLICT_PORT=6688
EVIDENCE_LOG="${EVIDENCE_LOG_FIXTURE}"
ORIGINAL_COMMAND="${ORIGINAL_COMMAND_FIXTURE}"
APP_PATH="/tmp/Ava.app"
emit "Evidence log: ${EVIDENCE_LOG}"
emit "Date: 2026-05-13T00:00:00Z"
emit "Command: ${ORIGINAL_COMMAND}"
emit "App path: ${APP_PATH}"
emit "Skip build: ${SKIP_BUILD_FIXTURE}"
emit "With port conflict: ${WITH_PORT_CONFLICT}"
emit "Conflict port: ${PORT_CONFLICT_PORT}"
if [[ "${WITH_PORT_CONFLICT}" == "1" ]]; then
  emit "127.0.0.1:${PORT_CONFLICT_PORT} is occupied by temporary non-Ava server"
fi
print_manual_checklist
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "FUNCTIONS_FILE": str(functions_file),
                "EVIDENCE_LOG_FIXTURE": str(path),
                "ORIGINAL_COMMAND_FIXTURE": expected_command(path, with_port_conflict=with_port_conflict),
                "SKIP_BUILD_FIXTURE": "1" if with_port_conflict else "0",
                "WITH_PORT_CONFLICT_FIXTURE": "1" if with_port_conflict else "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stdout

    def filled_record(path: Path, *, with_port_conflict: bool) -> str:
        command = expected_command(path, with_port_conflict=with_port_conflict)
        conflict_port = "6688" if with_port_conflict else "not run by this command"
        dynamic_port = (
            "automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688"
            if with_port_conflict
            else "not run by this command"
        )
        return f"""Date: 2026-05-13T00:00:00Z
Command: {command}
App path: /tmp/Ava.app
Evidence log: {path}
Conflict port: {conflict_port}
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: {dynamic_port}
Finder double-click, no Terminal: Confirmed no Terminal window opened
Setup surface visible before Console: Confirmed setup surface appears before Console
Cancel stops uv sync, Retry starts again: Confirmed Cancel and Retry behavior
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed logs folder opened
Notes / log excerpts:
"""

    generate_log(happy_log, with_port_conflict=False)
    generate_log(port_log, with_port_conflict=True)
    doc.write_text(
        f"""## Result Records

{filled_record(happy_log, with_port_conflict=False)}
{filled_record(port_log, with_port_conflict=True)}
""",
        encoding="utf-8",
    )
    task.write_text(
        f"## 8. Objective Completion Audit\n\n{doc.read_text(encoding='utf-8')}",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "scripts/verify-desktop-closeout-records.sh",
            str(happy_log),
            str(port_log),
            str(doc),
            str(task),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "Desktop closeout records verified" in result.stdout


def test_desktop_acceptance_conflict_port_override_is_source_only(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    prefix = acceptance.split("while [[ $# -gt 0 ]]", 1)[0]
    snippet = tmp_path / "acceptance-prefix.sh"
    snippet.write_text(f"{prefix}\nprintf '%s\\n' \"${{PORT_CONFLICT_PORT}}\"\n", encoding="utf-8")
    env = {
        **os.environ,
        "AVA_DESKTOP_VERIFY_ALLOW_CONFLICT_PORT_OVERRIDE": "1",
        "AVA_DESKTOP_VERIFY_CONFLICT_PORT": "6699",
    }

    executed = subprocess.run(
        ["bash", str(snippet)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert executed.returncode == 0, executed.stdout
    assert executed.stdout.strip() == "6688"

    sourced = subprocess.run(
        ["bash", "-c", 'source "$SNIPPET"'],
        cwd=ROOT,
        env={**env, "SNIPPET": str(snippet)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert sourced.returncode == 0, sourced.stdout
    assert sourced.stdout.strip() == "6699"


def test_desktop_acceptance_manual_checklist_reports_dynamic_port_detail(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    assert "`scripts/verify-desktop-handoff-ready.sh --port-conflict`" not in acceptance
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    evidence_log = tmp_path / "successful-acceptance.log"
    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
WITH_PORT_CONFLICT=1
PORT_CONFLICT_PORT=6699
EVIDENCE_LOG="${EVIDENCE_LOG_FIXTURE}"
ORIGINAL_COMMAND="scripts/verify-desktop-acceptance.sh --with-port-conflict"
APP_PATH="/tmp/Ava.app"
print_manual_checklist
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "EVIDENCE_LOG_FIXTURE": str(evidence_log),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "Full desktop acceptance is not complete until the manual visual fields below are filled." in result.stdout
    assert "run scripts/verify-desktop-handoff-ready.sh --port-conflict first" in result.stdout
    assert "Dynamic-port path: automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6699" in result.stdout
    assert "Conflict port: 6699" in result.stdout
    assert "Finder double-click, no Terminal:\nSetup surface visible before Console:\nCancel stops uv sync, Retry starts again:\nHelp -> Open Logs opens ~/Library/Logs/Ava:\nNotes / log excerpts:" in result.stdout
    assert "Paste-ready result record:" in result.stdout
    assert "```text" in result.stdout
    log = evidence_log.read_text(encoding="utf-8")
    assert "Paste-ready result record:" in log
    assert "run scripts/verify-desktop-handoff-ready.sh --port-conflict first" in log
    assert "Finder double-click, no Terminal:\nSetup surface visible before Console:\nCancel stops uv sync, Retry starts again:\nHelp -> Open Logs opens ~/Library/Logs/Ava:\nNotes / log excerpts:" in log
    assert "Automated desktop acceptance checks failed" not in log

    happy_log = tmp_path / "successful-happy-acceptance.log"
    happy_script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
WITH_PORT_CONFLICT=0
PORT_CONFLICT_PORT=6699
EVIDENCE_LOG="${EVIDENCE_LOG_FIXTURE}"
ORIGINAL_COMMAND="scripts/verify-desktop-acceptance.sh"
APP_PATH="/tmp/Ava.app"
print_manual_checklist
"""
    happy = subprocess.run(
        ["bash", "-c", happy_script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "EVIDENCE_LOG_FIXTURE": str(happy_log),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert happy.returncode == 0, happy.stdout
    assert "Dynamic-port path: not run by this command" in happy.stdout
    assert "Conflict port: not run by this command" in happy.stdout
    assert "Conflict port: 6699" not in happy.stdout


def test_desktop_launch_verifier_log_rotation_functions_are_executable(tmp_path: Path) -> None:
    verifier = read("scripts/verify-desktop-launch.sh")
    functions = verifier.split('[[ -d "${APP_PATH}" ]]', 1)[0]
    functions_file = tmp_path / "verify-desktop-launch-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    main_log = tmp_path / "main.log"
    core_log = tmp_path / "core.log"
    text_executable = tmp_path / "not-mach-o"
    text_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    text_executable.chmod(0o755)
    main_log.write_text(
        "launch config repoRootFound=true externalCore=false coreEndpoint=http://127.0.0.1:1111\n",
        encoding="utf-8",
    )
    core_log.write_text("old core\n", encoding="utf-8")
    output_file = tmp_path / "core-error.out"

    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
set +e
( require_mach_o_executable "${TEXT_EXECUTABLE}" ) >"${OUTPUT_FILE}" 2>&1
status="$?"
set -e
[[ "${status}" == "1" ]] || {
  echo "non-Mach-O executable check returned ${status}"
  exit 1
}
grep -q "main executable is not a Mach-O binary" "${OUTPUT_FILE}"
MAIN_LOG="${MAIN_LOG_FIXTURE}"
CORE_LOG="${CORE_LOG_FIXTURE}"
MAIN_LOG_SIZE="$(log_size "${MAIN_LOG}")"
CORE_LOG_SIZE="$(log_size "${CORE_LOG}")"
MAIN_LOG_ID="$(log_identity "${MAIN_LOG}")"
CORE_LOG_ID="$(log_identity "${CORE_LOG}")"
rm "${MAIN_LOG}"
cat >"${MAIN_LOG}" <<'LOG'
launch config repoRootFound=true externalCore=true coreEndpoint=http://127.0.0.1:5544
LOG
rm "${CORE_LOG}"
cat >"${CORE_LOG}" <<'LOG'
Gateway crashed unexpectedly
LOG
endpoint="$(latest_endpoint_from_new_log)"
[[ "${endpoint}" == "http://127.0.0.1:5544" ]] || {
  echo "wrong endpoint: ${endpoint}"
  exit 1
}
[[ "$(endpoint_port "http://127.0.0.1:6688")" == "6688" ]] || {
  echo "wrong endpoint port parser"
  exit 1
}
FORBID_ENDPOINT_PORT=6688
forbidden_endpoint_port_selected "http://127.0.0.1:6688" || {
  echo "forbidden endpoint port was not detected"
  exit 1
}
! forbidden_endpoint_port_selected "http://127.0.0.1:5544" || {
  echo "allowed endpoint port was rejected"
  exit 1
}
REQUIRE_FRESH_CORE=1
fresh_core_required_but_reused_existing || {
  echo "externalCore=true was not rejected when fresh core is required"
  exit 1
}
set +e
( fail_on_new_core_errors ) >"${OUTPUT_FILE}" 2>&1
status="$?"
set -e
[[ "${status}" == "1" ]] || {
  echo "core error check returned ${status}"
  exit 1
}
grep -q "Gateway crashed unexpectedly" "${OUTPUT_FILE}"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "MAIN_LOG_FIXTURE": str(main_log),
            "CORE_LOG_FIXTURE": str(core_log),
            "OUTPUT_FILE": str(output_file),
            "TEXT_EXECUTABLE": str(text_executable),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_desktop_acceptance_runtime_meta_preflight_allows_missing_metadata(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    ava_home = tmp_path / "ava-home"
    ava_home.mkdir()
    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
AVA_HOME="${AVA_HOME_FIXTURE}"
EVIDENCE_LOG=""
fail_if_runtime_meta_has_healthy_core
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "AVA_HOME_FIXTURE": str(ava_home),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_desktop_acceptance_runtime_meta_preflight_blocks_healthy_core(tmp_path: Path) -> None:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ready": True,
                "shutting_down": False,
                "boot_generation": 1,
            }).encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")
    ava_home = tmp_path / "ava-home"
    ava_home.mkdir()

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        (ava_home / "console.json").write_text(
            json.dumps({"console_host": "127.0.0.1", "console_port": port}),
            encoding="utf-8",
        )
        script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
AVA_HOME="${AVA_HOME_FIXTURE}"
EVIDENCE_LOG=""
fail_if_runtime_meta_has_healthy_core
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "FUNCTIONS_FILE": str(functions_file),
                "AVA_HOME_FIXTURE": str(ava_home),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 1, result.stdout
    assert "runtime metadata points to an existing healthy Ava core" in result.stdout


def test_desktop_acceptance_conflict_port_preflight_blocks_healthy_core_without_metadata(tmp_path: Path) -> None:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ready": True,
                "shutting_down": False,
                "boot_generation": 1,
            }).encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG=""
PORT_CONFLICT_PORT="${PORT_CONFLICT_PORT_FIXTURE}"
fail_if_conflict_port_has_healthy_core
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={
                **os.environ,
                "FUNCTIONS_FILE": str(functions_file),
                "PORT_CONFLICT_PORT_FIXTURE": str(port),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 1, result.stdout
    assert f"127.0.0.1:{port} already hosts a healthy Ava core" in result.stdout


def test_desktop_acceptance_port_conflict_helper_serves_controlled_marker(tmp_path: Path) -> None:
    acceptance = read("scripts/verify-desktop-acceptance.sh")
    functions = acceptance.split('cd "${REPO_ROOT}"', 1)[0]
    functions_file = tmp_path / "verify-desktop-acceptance-functions.sh"
    functions_file.write_text(functions, encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    script = r"""
set -euo pipefail
source "${FUNCTIONS_FILE}"
EVIDENCE_LOG=""
AVA_DESKTOP_VERIFY_ALLOW_CONFLICT_PORT_OVERRIDE=1
PORT_CONFLICT_PORT="${PORT_CONFLICT_PORT_FIXTURE}"
start_port_conflict_server
body="$(curl -fsS "http://127.0.0.1:${PORT_CONFLICT_PORT}/ava-port-conflict.txt")"
[[ "${body}" == "${PORT_CONFLICT_MARKER}" ]] || {
  echo "wrong marker body: ${body}"
  exit 1
}
cleanup
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "FUNCTIONS_FILE": str(functions_file),
            "PORT_CONFLICT_PORT_FIXTURE": str(port),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert f"127.0.0.1:{port} is occupied by temporary non-Ava server" in result.stdout


def test_desktop_setup_surface_verifier_script_contract() -> None:
    verifier = read("scripts/verify-desktop-setup-surface.sh")
    dom_verifier = read("scripts/verify-desktop-setup-dom.mjs")
    assert_contains_all(
        verifier,
        [
            "mainWindow.loadFile(path.join(__dirname, 'setup.html'))",
            "SETUP_LOAD_TIMEOUT_MS",
            "dialog.showErrorBox('Ava setup failed to load'",
            "function showFatalStartupError(error)",
            "dialog.showErrorBox('Ava startup failed'",
            ".catch(showFatalStartupError)",
            "ipcMain.handle('ava:setNanobotRoot'",
            "ipcMain.handle('ava:retryCore'",
            "ipcMain.handle('ava:cancelBootstrap'",
            "saveNanobotRoot(app.getPath('appData'), root)",
            "validateNanobotRoot(nanobotRoot)",
            "window.avaDesktop?.onBootstrapState",
            "window.avaDesktop.setNanobotRoot",
            "window.avaDesktop.retryCore",
            "window.avaDesktop.cancelBootstrap",
            "LC_ALL=C strings",
            "desktop-config.mjs",
            "launch-env.mjs",
            "export function resolveLaunchPath",
            "function findCachedElectronZipDir(cacheRoot, version",
            "--electron-zip-dir=",
            "active.child.kill('SIGKILL')",
            "label: 'Open Logs'",
            "label: 'Retry Core'",
            "Menu.setApplicationMenu(menu)",
            "if (process.platform !== 'darwin')",
            "app.on('activate', () => {",
            "const RING_BUFFER_BYTES = 256 * 1024",
            "function appendRingBuffer(buffer, chunk, maxBytes = RING_BUFFER_BYTES)",
            "stderrTail = appendRingBuffer(stderrTail, chunk)",
            "detailParts.join('\\\\n\\\\n').slice(0, RING_BUFFER_BYTES)",
            "buttons: ['Retry', 'Pick nanobot', 'Open logs', 'Quit']",
        ],
    )
    assert_contains_all(
        dom_verifier,
        [
            "vm.runInContext",
            "avaDesktop:",
            "onBootstrapState(callback)",
            "readDesktopConfig()",
            "selectDirectory()",
            "setNanobotRoot(root)",
            "retryCore()",
            "cancelBootstrap()",
            "openLogs()",
            "Python environment bootstrap canceled",
            "canceled state did not render",
            "Desktop setup DOM behavior verified",
        ],
    )
    result = subprocess.run(
        ["bash", "-n", "scripts/verify-desktop-setup-surface.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    result = subprocess.run(
        ["node", "scripts/verify-desktop-setup-dom.mjs"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout


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
