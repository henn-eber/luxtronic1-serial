"""Pytest configuration — PHACC harness (homeassistant 2026.7.4)."""

from pathlib import Path
import sys

# Ensure custom_components and tests are importable (PHACC loader + emulator)
ROOT = Path(__file__).resolve().parent.parent
PKG_PARENT = ROOT / "custom_components"
if str(PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(PKG_PARENT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest_plugins = "pytest_homeassistant_custom_component"

# PHACC requires this fixture to load custom integrations
# Tests that use `hass` must include `enable_custom_integrations` as arg.
# Auto-enable for all tests via fixture below, but keep explicit for clarity.

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
