"""Shared device descriptor for the Luxtronik 1 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the DeviceInfo shared by all entities of a config entry.

    All entities use the same identifiers so they are grouped under one
    device in the device registry. The serial port is part of the
    connection info (not the identifier) since USB paths can change.
    """

    port: str = entry.data.get("serial_port", "unknown")
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        model="Luxtronik 1",
        name=f"Heat Pump ({port})",
    )


def unique_id(entry: ConfigEntry, key: str) -> str:
    """Stable unique_id for an entity key within a config entry."""

    base = entry.unique_id or entry.entry_id
    return f"{base}_{key}"