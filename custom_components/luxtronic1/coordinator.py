"""DataUpdateCoordinator for the Luxtronik 1 integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import LuxtronikClient
from .const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    DEFAULT_BAUDRATE,
    DEFAULT_PARITY,
    DEFAULT_READ_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DOMAIN,
)
from .models import (
    BWSchedule,
    HeatingCurve,
    Overview,
    TempSettings,
)
from .transport import LuxtronikConnectionError, LuxtronikTransport, SerialConfig

_LOGGER = logging.getLogger(__name__)


class LuxtronikCoordinator(DataUpdateCoordinator):
    """Owns the transport, client and the latest polled snapshot."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        serial_config = SerialConfig(
            url=entry.data[CONF_SERIAL_PORT],
            baudrate=int(entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
            parity=entry.data.get(CONF_PARITY, DEFAULT_PARITY),
            stopbits=int(entry.data.get(CONF_STOPBITS, DEFAULT_STOPBITS)),
        )

        self._transport = LuxtronikTransport(hass, serial_config)
        self.client = LuxtronikClient(
            self._transport,
            read_only=entry.options.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
            # All models are dataclasses comparable via __eq__, so skip
            # listener callbacks and state writes when nothing changed.
            always_update=False,
        )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._transport.async_close()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            overview: Overview = await self.client.read_overview()
            heating_mode = await self.client.read_heating_mode()
            hotwater_mode = await self.client.read_hotwater_mode()
            temp_settings: TempSettings = await self.client.read_temp_settings()
            heating_curve: HeatingCurve = await self.client.read_heating_curve()
            bw_schedule: BWSchedule = await self.client.read_bw_schedule()
        except LuxtronikConnectionError as exc:
            raise UpdateFailed(f"Communication error: {exc}") from exc

        return {
            "overview": overview,
            "heating_mode": heating_mode,
            "hotwater_mode": hotwater_mode,
            "temp_settings": temp_settings,
            "heating_curve": heating_curve,
            "bw_schedule": bw_schedule,
        }

    @property
    def read_only(self) -> bool:
        """Return True if writes to the controller are blocked."""
        return self.client.read_only

    # Convenience accessors used by entity platforms
    @property
    def overview(self) -> Overview:
        return self.data["overview"]

    @property
    def heating_mode(self) -> int:
        return self.data["heating_mode"]

    @property
    def hotwater_mode(self) -> int:
        return self.data["hotwater_mode"]

    @property
    def temp_settings(self) -> TempSettings:
        return self.data["temp_settings"]

    @property
    def heating_curve(self) -> HeatingCurve:
        return self.data["heating_curve"]

    @property
    def bw_schedule(self) -> BWSchedule:
        return self.data["bw_schedule"]