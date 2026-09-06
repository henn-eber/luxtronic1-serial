"""Tests for 779 (desync) recovery and climate preset modes."""
from __future__ import annotations
from luxtronic1.const import HEATING_PRESET_TO_MODE


def test_preset_modes_mapping() -> None:
    assert HEATING_PRESET_TO_MODE["backup_heater"] == 1
    assert HEATING_PRESET_TO_MODE["party"] == 2
    assert HEATING_PRESET_TO_MODE["holiday"] == 3
