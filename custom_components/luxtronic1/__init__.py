"""The Luxtronik 1 Heat Pump integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .services import async_register_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Luxtronik 1 integration.

    Services are registered here (not in async_setup_entry) so that
    automations referencing them can be validated even when no config
    entry is loaded yet.
    """

    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Luxtronik 1 from a config entry."""

    coordinator = LuxtronikCoordinator(hass, entry)
    # First refresh raises ConfigEntryNotReady on failure, which tells HA
    # to retry setup in the background instead of marking the entry failed.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
    return unload_ok