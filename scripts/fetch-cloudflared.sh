#!/usr/bin/env bash
set -euo pipefail

VERSION="${CLOUDFLARED_VERSION:-2026.3.0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor/cloudflared"
TMP_DIR="${TMPDIR:-/tmp}/ava-cloudflared-${VERSION}"
OFFLINE_PATH="${CLOUDFLARED_OFFLINE_PATH:-}"

platforms=("$@")
if [ "${#platforms[@]}" -eq 0 ]; then
  platforms=("darwin-arm64" "darwin-amd64" "linux-arm64" "linux-amd64" "windows-amd64")
fi

asset_for_platform() {
  case "$1" in
    darwin-arm64) echo "cloudflared-darwin-arm64.tgz" ;;
    darwin-amd64) echo "cloudflared-darwin-amd64.tgz" ;;
    linux-arm64) echo "cloudflared-linux-arm64" ;;
    linux-amd64) echo "cloudflared-linux-amd64" ;;
    windows-amd64) echo "cloudflared-windows-amd64.exe" ;;
    *) echo "unsupported platform: $1" >&2; exit 2 ;;
  esac
}

checksum_for_asset() {
  local asset="$1"
  python3 - "$asset" "$VERSION" <<'PY'
import re
import sys
import urllib.request

asset = sys.argv[1]
version = sys.argv[2]
url = f"https://github.com/cloudflare/cloudflared/releases/tag/{version}"
html = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", errors="replace")
match = re.search(rf"{re.escape(asset)}:\s*([0-9a-f]{{64}})", html)
if not match:
    raise SystemExit(f"missing SHA256 checksum for {asset} in {url}")
print(match.group(1))
PY
}

install_asset() {
  local platform="$1"
  local asset
  asset="$(asset_for_platform "$platform")"
  local url="https://github.com/cloudflare/cloudflared/releases/download/${VERSION}/${asset}"
  local target_dir="$VENDOR_DIR/$platform"
  local archive="$TMP_DIR/$asset"
  mkdir -p "$TMP_DIR" "$target_dir"

  if [ -n "$OFFLINE_PATH" ]; then
    if [ ! -f "$OFFLINE_PATH" ]; then
      echo "CLOUDFLARED_OFFLINE_PATH not found: $OFFLINE_PATH" >&2
      exit 1
    fi
    archive="$OFFLINE_PATH"
  elif [ ! -f "$archive" ]; then
    curl -fsSL "$url" -o "$archive"
  fi
  if [ -z "$OFFLINE_PATH" ]; then
    local expected
    expected="$(checksum_for_asset "$asset")"
    local actual
    actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
    if [ "$actual" != "$expected" ]; then
      echo "checksum mismatch for $asset: expected $expected, got $actual" >&2
      exit 1
    fi
  fi

  if [[ "$asset" == *.tgz ]]; then
    tar -xzf "$archive" -C "$target_dir"
    chmod +x "$target_dir/cloudflared"
  elif [[ "$asset" == *.exe ]]; then
    cp "$archive" "$target_dir/cloudflared.exe"
  else
    cp "$archive" "$target_dir/cloudflared"
    chmod +x "$target_dir/cloudflared"
  fi
  echo "installed cloudflared $VERSION for $platform"
}

for platform in "${platforms[@]}"; do
  install_asset "$platform"
done
