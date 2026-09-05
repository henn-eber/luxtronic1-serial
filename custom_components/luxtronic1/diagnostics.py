"""Diagnostics support for the Luxtronik 1 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL_PORT
from .coordinator import LuxtronikCoordinator


def _redact(value: str) -> str:
    """Redact a serial device path, keeping only the last segment."""
    return value.split("/")[-1] if "/" in value else value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: LuxtronikCoordinator = entry.runtime_data
    data = coordinator.data or {}

    overview = data.get("overview")
    diagnostics: dict[str, Any] = {
        "entry": {
            "serial_port": _redact(str(entry.data.get(CONF_SERIAL_PORT, "?"))),
            "scan_interval": entry.options.get("scan_interval"),
        },
        "heating_mode": data.get("heating_mode"),
        "hotwater_mode": data.get("hotwater_mode"),
    }
    if overview is not None:
        diagnostics["temperatures"] = {
            name: getattr(overview.temperatures, name)
            for name in (
                "flow",
                "return_",
                "return_setpoint",
                "hot_gas",
                "outdoor",
                "dhw_actual",
                "dhw_setpoint",
                "source_in",
                "source_out",
            )
        }
        diagnostics["status"] = {
            "anl_status": overview.status.anl_status,
            "anl_status_text": overview.status.anl_status_text,
            "software_version": overview.status.software_version,
        }
        diagnostics["errors"] = [
            {"code": e.code, "text": e.text, "timestamp": e.timestamp}
            for e in overview.errors
        ]
    return diagnostics
