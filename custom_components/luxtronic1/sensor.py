"""Sensor entity platform for Luxtronik 1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LuxtronikCoordinator
from .device import device_info, unique_id


@dataclass(frozen=True, kw_only=True)
class LuxtronikSensorDescription(SensorEntityDescription):
    """Describes a Luxtronik sensor with a value extractor."""

    value_fn: Callable[[LuxtronikCoordinator], float | int | str | None]


SENSORS: tuple[LuxtronikSensorDescription, ...] = (
    LuxtronikSensorDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.outdoor / 10,
    ),
    LuxtronikSensorDescription(
        key="flow_temperature",
        translation_key="flow_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.flow / 10,
    ),
    LuxtronikSensorDescription(
        key="return_temperature",
        translation_key="return_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.return_ / 10,
    ),
    LuxtronikSensorDescription(
        key="return_setpoint",
        translation_key="return_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.return_setpoint / 10,
    ),
    LuxtronikSensorDescription(
        key="hot_gas_temperature",
        translation_key="hot_gas_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.hot_gas / 10,
    ),
    LuxtronikSensorDescription(
        key="dhw_temperature",
        translation_key="dhw_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.dhw_actual / 10,
    ),
    LuxtronikSensorDescription(
        key="source_in_temperature",
        translation_key="source_in_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.source_in / 10,
    ),
    LuxtronikSensorDescription(
        key="source_out_temperature",
        translation_key="source_out_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.source_out / 10,
    ),
    LuxtronikSensorDescription(
        key="mix1_flow_actual",
        translation_key="mix1_flow_actual",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.mix1_flow_actual / 10,
    ),
    LuxtronikSensorDescription(
        key="mix1_flow_setpoint",
        translation_key="mix1_flow_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.mix1_flow_setpoint / 10,
    ),
    LuxtronikSensorDescription(
        key="dhw_setpoint",
        translation_key="dhw_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda c: c.overview.temperatures.dhw_setpoint / 10,
    ),
    LuxtronikSensorDescription(
        key="operating_state",
        translation_key="operating_state",
        device_class=SensorDeviceClass.ENUM,
        options=["Heating", "Hot water", "Swimming pool", "Utility lockout",
                 "Defrost", "Standby", "Unknown"],
        value_fn=lambda c: c.overview.status.anl_status_text,
    ),
    LuxtronikSensorDescription(
        key="heat_pump_total_hours",
        translation_key="heat_pump_total_hours",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda c: round(c.overview.hours.heat_pump_total / 3600, 1),
    ),
    LuxtronikSensorDescription(
        key="compressor_1_hours",
        translation_key="compressor_1_hours",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda c: round(c.overview.hours.compressor_1 / 3600, 1),
    ),
    LuxtronikSensorDescription(
        key="compressor_2_hours",
        translation_key="compressor_2_hours",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda c: round(c.overview.hours.compressor_2 / 3600, 1),
    ),
    LuxtronikSensorDescription(
        key="compressor_starts",
        translation_key="compressor_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: (
            c.overview.hours.compressor_1_starts + c.overview.hours.compressor_2_starts
        ),
    ),
    LuxtronikSensorDescription(
        key="software_version",
        translation_key="software_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.overview.status.software_version,
    ),
    LuxtronikSensorDescription(
        key="heat_pump_type",
        translation_key="heat_pump_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.overview.status.wp_type,
    ),
    LuxtronikSensorDescription(
        key="bivalent_stage",
        translation_key="bivalent_stage",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.overview.status.bivalent_stage,
    ),
    LuxtronikSensorDescription(
        key="runtime_wp_current",
        translation_key="runtime_wp_current",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.overview.runtimes.wp_seconds,
    ),
)

# The controller is a single serial line: serialize HA-level updates
# and service calls per platform as well (the transport locks too).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Luxtronik sensors from a config entry."""

    coordinator: LuxtronikCoordinator = entry.runtime_data
    async_add_entities(
        LuxtronikSensor(coordinator, entry, description)
        for description in SENSORS
    )


class LuxtronikSensor(CoordinatorEntity[LuxtronikCoordinator], SensorEntity):
    """A single read-only sensor backed by the coordinator data."""

    _attr_has_entity_name = True
    entity_description: LuxtronikSensorDescription

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
        description: LuxtronikSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id(entry, f"sensor_{description.key}")
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor from coordinator memory (no I/O)."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator)