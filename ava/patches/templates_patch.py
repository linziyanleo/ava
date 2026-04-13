"""
模板同步覆盖 Patch

只把 `TOOLS.md` 视为 sidecar 运行时事实源，启动时覆盖到 workspace。
其余 ava 模板仅在 workspace 缺失时补建，避免刷掉用户维护的人格/偏好文件。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from ava.launcher import register_patch

_AVA_TPL_DIR = Path(__file__).resolve().parent.parent / "templates"
_FORCE_OVERLAY_FILES = {"TOOLS.md"}


def apply_templates_patch() -> str:
    import nanobot.utils.helpers as helpers_mod
    import nanobot.cli.commands as commands_mod

    if getattr(helpers_mod.sync_workspace_templates, "_ava_templates_patched", False):
        return "templates_patch already applied (skipped)"

    _original_sync = helpers_mod.sync_workspace_templates

    def patched_sync(workspace: Path, silent: bool = False) -> list[str]:
        added = _original_sync(workspace, silent=silent)

        if not _AVA_TPL_DIR.is_dir():
            return added

        overlay_count = 0
        created_count = 0
        for src in _AVA_TPL_DIR.iterdir():
            if not src.name.endswith(".md") or src.name.startswith("."):
                continue
            dest = workspace / src.name
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.name in _FORCE_OVERLAY_FILES:
                    shutil.copy2(str(src), str(dest))
                    overlay_count += 1
                    continue
                if dest.exists():
                    continue
                shutil.copy2(str(src), str(dest))
                added.append(str(dest.relative_to(workspace)))
                created_count += 1
            except Exception as exc:
                logger.warning("templates_patch: failed to overlay {}: {}", src.name, exc)

        if (overlay_count or created_count) and not silent:
            logger.debug(
                "templates_patch: overlaid {} file(s), created {} supplemental file(s) from ava/templates/",
                overlay_count,
                created_count,
            )
        return added

    patched_sync._ava_templates_patched = True
    helpers_mod.sync_workspace_templates = patched_sync
    commands_mod.sync_workspace_templates = patched_sync

    return "sync_workspace_templates 已接管：仅 TOOLS.md 强制覆盖，其余 ava 模板仅补缺"


register_patch("templates_patch", apply_templates_patch)
