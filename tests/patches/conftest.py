"""Shared fixtures for patch tests.

Ensures schema fork is applied before tests that depend on it,
and restores it after tests that temporarily remove it.
"""

import sys
import pytest


@pytest.fixture(autouse=True, scope="session")
def _ensure_schema_fork():
    """Apply schema fork once at session start, restore after each test module."""
    from ava.patches.a_schema_patch import apply_schema_patch
    apply_schema_patch()
    yield
    # Re-apply to ensure it's active for any subsequent tests
    apply_schema_patch()
