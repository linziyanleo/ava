#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKSUMS_FILE="$ROOT_DIR/scripts/cloudflared-checksums.txt"

if [ ! -f "$CHECKSUMS_FILE" ]; then
  echo "missing checksums file: $CHECKSUMS_FILE" >&2
  exit 1
fi

PINNED_VERSION="$(awk -F= '/^VERSION=/{print $2; exit}' "$CHECKSUMS_FILE")"
if [ -z "$PINNED_VERSION" ]; then
  echo "VERSION not declared in $CHECKSUMS_FILE" >&2
  exit 1
fi

VERSION="${CLOUDFLARED_VERSION:-$PINNED_VERSION}"
if [ "$VERSION" != "$PINNED_VERSION" ]; then
  echo "CLOUDFLARED_VERSION=$VERSION does not match pinned $PINNED_VERSION." >&2
  echo "Update $CHECKSUMS_FILE before bumping cloudflared." >&2
  exit 1
fi

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
  local sha
  sha="$(awk -v target="$asset" '$2==target{print $1; exit}' "$CHECKSUMS_FILE")"
  if [ -z "$sha" ]; then
    echo "no pinned SHA256 for $asset in $CHECKSUMS_FILE" >&2
    return 1
  fi
  printf '%s' "$sha"
}

sha256_of() {
  shasum -a 256 "$1" | awk '{print $1}'
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
  else
    local expected
    expected="$(checksum_for_asset "$asset")"
    if [ -f "$archive" ] && [ "$(sha256_of "$archive")" != "$expected" ]; then
      echo "stale cache for $asset, redownloading" >&2
      rm -f "$archive"
    fi
    if [ ! -f "$archive" ]; then
      curl -fsSL "$url" -o "$archive"
    fi
    local actual
    actual="$(sha256_of "$archive")"
    if [ "$actual" != "$expected" ]; then
      echo "checksum mismatch for $asset: expected $expected, got $actual" >&2
      echo "Verify $CHECKSUMS_FILE matches the upstream release ${VERSION}." >&2
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
