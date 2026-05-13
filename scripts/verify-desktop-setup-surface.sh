#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="${1:-${REPO_ROOT}/electron/dist/Ava-darwin-arm64/Ava.app}"

fail() {
  echo "verify-desktop-setup-surface: $*" >&2
  exit 1
}

require_file() {
  local file="$1"
  [[ -f "${file}" ]] || fail "missing file: ${file}"
}

require_contains() {
  local file="$1"
  local needle="$2"
  grep -Fq -- "${needle}" "${file}" || fail "${file} missing: ${needle}"
}

MAIN="${REPO_ROOT}/electron/main.mjs"
PRELOAD="${REPO_ROOT}/electron/preload.cjs"
SETUP="${REPO_ROOT}/electron/setup.html"
DESKTOP_CONFIG="${REPO_ROOT}/electron/lib/desktop-config.mjs"
LAUNCH_ENV="${REPO_ROOT}/electron/lib/launch-env.mjs"
RUNTIME_MANIFEST="${REPO_ROOT}/electron/lib/runtime-manifest.mjs"
BUILD_SCRIPT="${REPO_ROOT}/electron/scripts/build.mjs"
APP_ASAR="${APP_PATH}/Contents/Resources/app.asar"
PACKAGED_RUNTIME_MANIFEST="${APP_PATH}/Contents/Resources/ava-runtime-manifest.json"

require_file "${MAIN}"
require_file "${PRELOAD}"
require_file "${SETUP}"
require_file "${DESKTOP_CONFIG}"
require_file "${LAUNCH_ENV}"
require_file "${RUNTIME_MANIFEST}"
require_file "${BUILD_SCRIPT}"
require_file "${APP_ASAR}"
require_file "${PACKAGED_RUNTIME_MANIFEST}"

require_contains "${MAIN}" "mainWindow.loadFile(path.join(__dirname, 'setup.html'))"
require_contains "${MAIN}" "SETUP_LOAD_TIMEOUT_MS"
require_contains "${MAIN}" "did-finish-load"
require_contains "${MAIN}" "did-fail-load"
require_contains "${MAIN}" "clearTimeout(setupLoadTimeout)"
require_contains "${MAIN}" "dialog.showErrorBox('Ava setup failed to load'"
require_contains "${MAIN}" "function showFatalStartupError(error)"
require_contains "${MAIN}" "dialog.showErrorBox('Ava startup failed'"
require_contains "${MAIN}" ".catch(showFatalStartupError)"
require_contains "${MAIN}" "ipcMain.handle('ava:setNanobotRoot'"
require_contains "${MAIN}" "ipcMain.handle('ava:retryCore'"
require_contains "${MAIN}" "ipcMain.handle('ava:cancelBootstrap'"
require_contains "${MAIN}" "saveNanobotRoot(app.getPath('appData'), root)"
require_contains "${MAIN}" "validateNanobotRoot(nanobotRoot)"
require_contains "${MAIN}" "active.child.kill('SIGTERM')"
require_contains "${MAIN}" "active.child.kill('SIGKILL')"
require_contains "${MAIN}" "label: 'Help'"
require_contains "${MAIN}" "label: 'Open Logs'"
require_contains "${MAIN}" "Menu.setApplicationMenu(menu)"
require_contains "${MAIN}" "const RING_BUFFER_BYTES = 256 * 1024"
require_contains "${MAIN}" "function appendRingBuffer(buffer, chunk, maxBytes = RING_BUFFER_BYTES)"
require_contains "${MAIN}" "stderrTail = appendRingBuffer(stderrTail, chunk)"
require_contains "${MAIN}" "detailParts.join('\\n\\n').slice(0, RING_BUFFER_BYTES)"
require_contains "${MAIN}" "buttons: ['Retry', 'Pick nanobot', 'Open logs', 'Quit']"
require_contains "${MAIN}" "from './lib/runtime-manifest.mjs'"
require_contains "${MAIN}" "readRuntimeManifestRepoRoot(runtimeManifestPaths(__dirname))"

require_contains "${DESKTOP_CONFIG}" "export function validateNanobotRoot(root)"
require_contains "${DESKTOP_CONFIG}" "export function saveNanobotRoot(appDataPath, root"
require_contains "${DESKTOP_CONFIG}" "export function resolveNanobotCandidate"

require_contains "${LAUNCH_ENV}" "export function resolveLaunchPath"
require_contains "${LAUNCH_ENV}" "export function findExecutable(command, env)"
require_contains "${LAUNCH_ENV}" "export function buildCoreEnv(config, nanobotRoot)"
require_contains "${LAUNCH_ENV}" "AVA_DESKTOP_CONSOLE_PORT: String(config.port)"

require_contains "${RUNTIME_MANIFEST}" "export const RUNTIME_MANIFEST_NAME = 'ava-runtime-manifest.json'"
require_contains "${RUNTIME_MANIFEST}" "export function readRuntimeManifestRepoRoot"

require_contains "${BUILD_SCRIPT}" "function findCachedElectronZipDir(cacheRoot, version"
require_contains "${BUILD_SCRIPT}" "--electron-zip-dir="
require_contains "${BUILD_SCRIPT}" "--download.cacheRoot"
require_contains "${BUILD_SCRIPT}" "--extra-resource="
require_contains "${BUILD_SCRIPT}" "invalid runtime manifest repoRoot"

require_contains "${PRELOAD}" "contextBridge.exposeInMainWorld('avaDesktop', api)"
require_contains "${PRELOAD}" "setNanobotRoot"
require_contains "${PRELOAD}" "retryCore"
require_contains "${PRELOAD}" "cancelBootstrap"
require_contains "${PRELOAD}" "onBootstrapState"

require_contains "${SETUP}" "Ava Setup"
require_contains "${SETUP}" "Select Nanobot"
require_contains "${SETUP}" "window.avaDesktop?.onBootstrapState"
require_contains "${SETUP}" "window.avaDesktop.setNanobotRoot"
require_contains "${SETUP}" "window.avaDesktop.retryCore"
require_contains "${SETUP}" "window.avaDesktop.cancelBootstrap"
require_contains "${SETUP}" "window.avaDesktop.openLogs"

ASAR_STRINGS="$(mktemp "${TMPDIR:-/tmp}/ava-app-asar.XXXXXX")"
trap 'rm -f "${ASAR_STRINGS}"' EXIT
LC_ALL=C strings "${APP_ASAR}" >"${ASAR_STRINGS}"

require_contains "${ASAR_STRINGS}" "setup.html"
require_contains "${ASAR_STRINGS}" "Ava Setup"
require_contains "${ASAR_STRINGS}" "window.avaDesktop.cancelBootstrap"
require_contains "${ASAR_STRINGS}" "desktop-config.mjs"
require_contains "${ASAR_STRINGS}" "export function saveNanobotRoot"
require_contains "${ASAR_STRINGS}" "launch-env.mjs"
require_contains "${ASAR_STRINGS}" "runtime-manifest.mjs"
require_contains "${ASAR_STRINGS}" "export function resolveLaunchPath"
require_contains "${ASAR_STRINGS}" "readRuntimeManifestRepoRoot"
require_contains "${ASAR_STRINGS}" "AVA_DESKTOP_CONSOLE_PORT: String(config.port)"
require_contains "${PACKAGED_RUNTIME_MANIFEST}" '"repoRoot"'
require_contains "${ASAR_STRINGS}" "ava:cancelBootstrap"
require_contains "${ASAR_STRINGS}" "Setup surface did not finish loading"
require_contains "${ASAR_STRINGS}" "dialog.showErrorBox('Ava setup failed to load'"
require_contains "${ASAR_STRINGS}" "function showFatalStartupError(error)"
require_contains "${ASAR_STRINGS}" "dialog.showErrorBox('Ava startup failed'"
require_contains "${ASAR_STRINGS}" ".catch(showFatalStartupError)"
require_contains "${ASAR_STRINGS}" "active.child.kill('SIGKILL')"
require_contains "${ASAR_STRINGS}" "label: 'Open Logs'"
require_contains "${ASAR_STRINGS}" "Menu.setApplicationMenu(menu)"
require_contains "${ASAR_STRINGS}" "const RING_BUFFER_BYTES = 256 * 1024"
require_contains "${ASAR_STRINGS}" "function appendRingBuffer(buffer, chunk, maxBytes = RING_BUFFER_BYTES)"
require_contains "${ASAR_STRINGS}" "stderrTail = appendRingBuffer(stderrTail, chunk)"
require_contains "${ASAR_STRINGS}" "detailParts.join('\\n\\n').slice(0, RING_BUFFER_BYTES)"
require_contains "${ASAR_STRINGS}" "buttons: ['Retry', 'Pick nanobot', 'Open logs', 'Quit']"

echo "Desktop setup surface is wired and packaged in ${APP_PATH}"
