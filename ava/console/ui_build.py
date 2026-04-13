"""console-ui 构建产物新鲜度检查与按需重建。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

ConsoleUiBuildRunner = Callable[[Path], None]

_CONSOLE_UI_DIR = Path(__file__).resolve().parents[2] / "console-ui"
_SOURCE_PATHS = (
    "src",
    "public",
    "index.html",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "eslint.config.js",
)


def prepare_console_ui_dist(
    console_ui_dir: Path | None = None,
    build_runner: ConsoleUiBuildRunner | None = None,
) -> Path | None:
    """确保 `console-ui/dist` 可用；源码更新时自动重建。"""
    root = (console_ui_dir or _CONSOLE_UI_DIR).resolve()
    if not root.exists():
        logger.debug("console-ui directory not found: {}", root)
        return None

    dist_dir = root / "dist"
    try:
        if needs_console_ui_build(root):
            _build_console_ui(root, build_runner=build_runner)
    except Exception as exc:
        logger.warning("console-ui build failed: {}", exc)

    if (dist_dir / "index.html").is_file():
        return dist_dir

    logger.warning("console-ui dist unavailable, static UI will not be mounted: {}", dist_dir)
    return None


def needs_console_ui_build(console_ui_dir: Path) -> bool:
    """当源码比 `dist` 新，或 `dist` 缺失时返回 True。"""
    dist_dir = console_ui_dir / "dist"
    if not (dist_dir / "index.html").is_file():
        return True

    latest_source_mtime = _latest_mtime(_iter_source_files(console_ui_dir))
    latest_dist_mtime = _latest_mtime(_iter_files(dist_dir))

    if latest_source_mtime is None:
        return False
    if latest_dist_mtime is None:
        return True

    return latest_source_mtime > latest_dist_mtime


def _build_console_ui(
    console_ui_dir: Path,
    build_runner: ConsoleUiBuildRunner | None = None,
) -> None:
    logger.info("console-ui dist missing or stale, running npm build: {}", console_ui_dir)

    if build_runner is not None:
        build_runner(console_ui_dir)
        return

    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise RuntimeError("npm not found in PATH")

    completed = subprocess.run(
        [npm_bin, "run", "build"],
        cwd=console_ui_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return

    combined_output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    excerpt = "\n".join(combined_output.splitlines()[-30:]) if combined_output else "no output captured"
    raise RuntimeError(f"`npm run build` failed for {console_ui_dir}:\n{excerpt}")


def _iter_source_files(console_ui_dir: Path) -> Iterable[Path]:
    for relative_path in _SOURCE_PATHS:
        yield from _iter_path_files(console_ui_dir / relative_path)


def _iter_path_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        yield from _iter_files(path)


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _latest_mtime(paths: Iterable[Path]) -> int | None:
    latest: int | None = None
    for path in paths:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            continue
        if latest is None or mtime > latest:
            latest = mtime
    return latest


# ---------------------------------------------------------------------------
# 按需重建 + version.json
# ---------------------------------------------------------------------------

@dataclass
class RebuildResult:
    success: bool
    duration_ms: int = 0
    version_hash: str = ""
    error: str = ""
    log_tail: list[str] = field(default_factory=list)


_rebuild_lock = asyncio.Lock()


async def rebuild_console_ui(
    console_ui_dir: Path | None = None,
) -> RebuildResult:
    """异步触发 console-ui rebuild，复用 _build_console_ui 逻辑。

    同一时刻只允许一个 rebuild 进程（通过 asyncio.Lock 保护）。
    """
    root = (console_ui_dir or _CONSOLE_UI_DIR).resolve()
    if not root.exists():
        return RebuildResult(success=False, error=f"console-ui directory not found: {root}")

    if _rebuild_lock.locked():
        return RebuildResult(success=False, error="Rebuild already in progress")

    async with _rebuild_lock:
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _build_console_ui, root, None)
            duration_ms = int((time.monotonic() - t0) * 1000)
            ver_hash = write_version_json(root / "dist")
            return RebuildResult(
                success=True,
                duration_ms=duration_ms,
                version_hash=ver_hash,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            err_lines = str(exc).splitlines()
            return RebuildResult(
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
                log_tail=err_lines[-20:],
            )


def write_version_json(dist_dir: Path) -> str:
    """在 dist/ 下写入 version.json，返回 hash 值。"""
    content_hash = _compute_dist_hash(dist_dir)
    version_data = {
        "hash": content_hash,
        "timestamp": int(time.time()),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    version_file = dist_dir / "version.json"
    version_file.write_text(json.dumps(version_data, indent=2))
    logger.info("version.json written: hash={}", content_hash[:12])
    return content_hash


def _compute_dist_hash(dist_dir: Path) -> str:
    """基于 dist/assets/ 下所有文件内容的 sha256 摘要。"""
    h = hashlib.sha256()
    assets_dir = dist_dir / "assets"
    if not assets_dir.is_dir():
        h.update(b"no-assets")
        return h.hexdigest()[:16]
    for f in sorted(assets_dir.rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]
