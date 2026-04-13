"""Tests for b_config_patch — Config Schema field injection (fallback)."""

import sys

import pytest


class TestConfigPatch:
    def test_skip_when_fork_active(self):
        """T2.1: returns 'skipped' when _ava_fork is True."""
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.b_config_patch import apply_config_patch

        apply_schema_patch()
        result = apply_config_patch()
        assert "skipped" in result.lower()

    def test_inject_fields_when_no_fork(self):
        """T2.2: injects fields when fork is NOT active."""
        # Remove fork marker
        mod = sys.modules.get("nanobot.config.schema")
        orig_marker = getattr(mod, "_ava_fork", False)
        if mod:
            mod._ava_fork = False

        try:
            from ava.patches.b_config_patch import apply_config_patch

            result = apply_config_patch()
            # Should either inject or report already present
            assert "extended" in result.lower() or "already present" in result.lower()
        finally:
            if mod:
                mod._ava_fork = orig_marker

    def test_idempotent(self):
        """T2.3: repeated calls don't error."""
        mod = sys.modules.get("nanobot.config.schema")
        orig_marker = getattr(mod, "_ava_fork", False)
        if mod:
            mod._ava_fork = False

        try:
            from ava.patches.b_config_patch import apply_config_patch

            apply_config_patch()
            result = apply_config_patch()
            # Second call: fields already present
            assert "already present" in result.lower() or "extended" in result.lower()
        finally:
            if mod:
                mod._ava_fork = orig_marker
