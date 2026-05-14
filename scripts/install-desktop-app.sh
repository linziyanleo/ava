#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="${APP_PATH:-${REPO_ROOT}/electron/dist/Ava-darwin-arm64/Ava.app}"
TARGET_PATH="${TARGET_PATH:-/Applications/Ava.app}"
SKIP_BUILD=0

usage() {
  cat <<'USAGE'
Usage: scripts/install-desktop-app.sh [--skip-build]

Build Ava.app and install it to /Applications/Ava.app.

Environment:
  APP_PATH=/path/to/Ava.app       Source app bundle. Defaults to electron/dist/Ava-darwin-arm64/Ava.app.
  TARGET_PATH=/Applications/Ava.app
                                  Install destination.
USAGE
}

fail() {
  echo "install-desktop-app: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --)
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

if [[ -s "${HOME}/.nvm/nvm.sh" && -f "${REPO_ROOT}/.nvmrc" ]]; then
  # shellcheck source=/dev/null
  source "${HOME}/.nvm/nvm.sh"
  nvm use >/dev/null
fi

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  (cd "${REPO_ROOT}" && CI=true pnpm electron:build)
fi

[[ -d "${APP_PATH}" ]] || fail "missing built app bundle: ${APP_PATH}"
[[ -x "${APP_PATH}/Contents/MacOS/Ava" ]] || fail "missing app executable: ${APP_PATH}/Contents/MacOS/Ava"

codesign --verify --deep --strict --verbose=1 "${APP_PATH}"

if [[ -e "${TARGET_PATH}" ]]; then
  running_pids="$(lsof -t "${TARGET_PATH}/Contents/MacOS/Ava" 2>/dev/null || true)"
  if [[ -n "${running_pids}" ]]; then
    fail "${TARGET_PATH} is running (pid(s): ${running_pids//$'\n'/, }); quit Ava.app before installing"
  fi
  rm -rf "${TARGET_PATH}"
fi

ditto "${APP_PATH}" "${TARGET_PATH}"
codesign --verify --deep --strict --verbose=1 "${TARGET_PATH}"

echo "Installed ${APP_PATH} -> ${TARGET_PATH}"
