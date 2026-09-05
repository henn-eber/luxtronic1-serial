"""Binary sensor platform for Luxtronik 1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LuxtronikCoordinator
from .device import device_info, unique_id


@dataclass(frozen=True, kw_only=True)
class LuxtronikBinarySensorDescription(BinarySensorEntityDescription):
    """Description of a binary sensor."""

    value_fn: Callable[[LuxtronikCoordinator], bool]


# The controller is a single serial line: serialize HA-level updates
# as well (the transport locks too).
PARALLEL_UPDATES = 1


BINARY_SENSORS: tuple[LuxtronikBinarySensorDescription, ...] = (
    LuxtronikBinarySensorDescription(
        key="compressor_1",
        translation_key="compressor_1",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.overview.outputs.compressor_1,
    ),
    LuxtronikBinarySensorDescription(
        key="compressor_2",
        translation_key="compressor_2",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.overview.outputs.compressor_2,
    ),
    LuxtronikBinarySensorDescription(
        key="heating_pump",
        translation_key="heating_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.overview.outputs.heating_pump,
    ),
    LuxtronikBinarySensorDescription(
        key="dhw_pump",
        translation_key="dhw_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.overview.outputs.dhw_circulation_pump,
    ),
    LuxtronikBinarySensorDescription(
        key="defrost_valve",
        translation_key="defrost_valve",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda c: c.overview.outputs.defrost_valve,
    ),
    LuxtronikBinarySensorDescription(
        key="brine_pump",
        translation_key="brine_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.overview.outputs.brine_pump_or_source_fan,
    ),
    LuxtronikBinarySensorDescription(
        key="evu_lock",
        translation_key="evu_lock",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.overview.inputs.evu,
    ),
    LuxtronikBinarySensorDescription(
        key="high_pressure",
        translation_key="high_pressure",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.overview.inputs.hd,
    ),
    LuxtronikBinarySensorDescription(
        key="low_pressure",
        translation_key="low_pressure",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.overview.inputs.nd,
    ),
    LuxtronikBinarySensorDescription(
        key="motor_protection",
        translation_key="motor_protection",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.overview.inputs.mot,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: LuxtronikCoordinator = entry.runtime_data
    async_add_entities(
        LuxtronikBinarySensor(coordinator, entry, desc)
        for desc in BINARY_SENSORS
    )


class LuxtronikBinarySensor(
    CoordinatorEntity[LuxtronikCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    entity_description: LuxtronikBinarySensorDescription

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
        description: LuxtronikBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id(entry, f"binary_sensor_{description.key}")
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator)