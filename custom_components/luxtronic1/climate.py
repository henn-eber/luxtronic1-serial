"""Climate platform: heating mode + target temperature control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import LuxtronikReadOnlyError
from .const import (
    HEATING_MODES,
    HOTWATER_MODES,
    MODE_AUTO,
    MODE_OFF,
    MODE_ZWE,
)
from .coordinator import LuxtronikCoordinator
from .device import device_info, unique_id

_LOGGER = logging.getLogger(__name__)

# The controller is a single serial line: serialize HA-level updates
# and service calls as well (the transport locks too).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: LuxtronikCoordinator = entry.runtime_data
    async_add_entities([LuxtronikClimate(coordinator, entry)])


class LuxtronikClimate(CoordinatorEntity[LuxtronikCoordinator], ClimateEntity):
    """Heating-side climate entity with mode switch and target setpoint."""

    _attr_has_entity_name = True
    _attr_translation_key = "heating"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.OFF, HVACMode.HEAT]

    def __init__(
        self, coordinator: LuxtronikCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id(entry, "climate_heating")
        self._attr_device_info = device_info(entry)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Hide all controls while read-only mode blocks writes."""
        if self.coordinator.read_only:
            return ClimateEntityFeature(0)
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    @property
    def current_temperature(self) -> float:
        return self.coordinator.overview.temperatures.flow / 10

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.overview.temperatures.return_setpoint / 10

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self.coordinator.heating_mode
        if mode == MODE_OFF:
            return HVACMode.OFF
        if mode == MODE_AUTO:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if self.coordinator.overview.outputs.any_compressor_running:
            return HVACAction.HEATING
        if self.coordinator.overview.status.anl_status_text == "Hot water":
            return HVACAction.IDLE
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                await self.coordinator.client.set_heating_mode(MODE_OFF)
            elif hvac_mode == HVACMode.AUTO:
                await self.coordinator.client.set_heating_mode(MODE_AUTO)
            else:
                await self.coordinator.client.set_heating_mode(MODE_ZWE)
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to set heating mode")
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        target = kwargs.get("temperature")
        if target is None:
            return
        try:
            await self.coordinator.client.set_heating_curve(offset=target)
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to set heating curve offset")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self.coordinator.heating_mode
        return {
            "heating_mode_label": HEATING_MODES.get(mode, "Unknown"),
            "hotwater_mode_label": HOTWATER_MODES.get(
                self.coordinator.hotwater_mode, "Unknown"
            ),
        }

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None