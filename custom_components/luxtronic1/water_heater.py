"""Water heater platform for the DHW (Brauchwasser) circuit."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_ELECTRIC,
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import LuxtronikReadOnlyError
from .const import (
    MODE_AUTO,
    MODE_HOLIDAY,
    MODE_OFF,
    MODE_OFF_ALT,
    MODE_PARTY,
    MODE_ZWE,
)
from .coordinator import LuxtronikCoordinator
from .device import device_info, unique_id

_LOGGER = logging.getLogger(__name__)

# The controller is a single serial line: serialize HA-level updates
# and service calls as well (the transport locks too).
PARALLEL_UPDATES = 1

# Luxtronik numeric mode -> standard water_heater operation state.
# The base component forbids custom operation strings, so we map:
#   AUTO -> heat_pump, ZWE (backup heater) -> electric,
#   Party -> performance, Holiday -> eco, Off -> off.
MODE_TO_OPERATION: dict[int, str] = {
    MODE_AUTO: STATE_HEAT_PUMP,
    MODE_ZWE: STATE_ELECTRIC,
    MODE_PARTY: STATE_PERFORMANCE,
    MODE_HOLIDAY: STATE_ECO,
    MODE_OFF: STATE_OFF,
    MODE_OFF_ALT: STATE_OFF,
}
OPERATION_TO_MODE: dict[str, int] = {
    STATE_HEAT_PUMP: MODE_AUTO,
    STATE_ELECTRIC: MODE_ZWE,
    STATE_PERFORMANCE: MODE_PARTY,
    STATE_ECO: MODE_HOLIDAY,
    STATE_OFF: MODE_OFF,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: LuxtronikCoordinator = entry.runtime_data
    async_add_entities([LuxtronikWaterHeater(coordinator, entry)])


class LuxtronikWaterHeater(
    CoordinatorEntity[LuxtronikCoordinator], WaterHeaterEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "hot_water"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [
        STATE_HEAT_PUMP,
        STATE_ELECTRIC,
        STATE_PERFORMANCE,
        STATE_ECO,
        STATE_OFF,
    ]
    def __init__(
        self, coordinator: LuxtronikCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id(entry, "water_heater_dhw")
        self._attr_device_info = device_info(entry)

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Hide all controls while read-only mode blocks writes."""
        if self.coordinator.read_only:
            return WaterHeaterEntityFeature(0)
        return (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.overview.temperatures.dhw_actual / 10

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.overview.temperatures.dhw_setpoint / 10

    @property
    def min_temp(self) -> float:
        return 30.0

    @property
    def max_temp(self) -> float:
        return 65.0

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.hotwater_mode != MODE_OFF

    @property
    def current_operation(self) -> str | None:
        return MODE_TO_OPERATION.get(self.coordinator.hotwater_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        target = kwargs.get("temperature")
        if target is None:
            return
        try:
            await self.coordinator.client.set_dhw_setpoint(float(target))
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to set DHW setpoint")

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        mode = OPERATION_TO_MODE.get(operation_mode)
        if mode is None:
            return
        try:
            await self.coordinator.client.set_hotwater_mode(mode)
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to set hot water mode")

    async def async_turn_on(self) -> None:
        try:
            await self.coordinator.client.set_hotwater_mode(MODE_AUTO)
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to enable hot water")

    async def async_turn_off(self) -> None:
        try:
            await self.coordinator.client.set_hotwater_mode(MODE_OFF)
        except LuxtronikReadOnlyError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception:  # pragma: no cover
            _LOGGER.exception("Failed to disable hot water")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None