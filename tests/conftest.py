"""Pytest configuration - lightweight HA stubs."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG_PARENT = ROOT / "custom_components"
if str(PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(PKG_PARENT))


def _make_fake_module(name: str, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    # base package
    ha = _make_fake_module("homeassistant")
    # core
    def _callback(func):  # type: ignore[no-untyped-def]
        return func

    ha.core = _make_fake_module(
        "homeassistant.core",
        HomeAssistant=object,
        ServiceCall=object,
        callback=_callback,
    )
    # config_entries with proper base classes
    class _FakeConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):  # type: ignore[no-untyped-def]
            super().__init_subclass__(**kwargs)
            if domain is not None:
                cls.domain = domain

        def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
            self._unique_id = None
            self.hass = None
            self.config_entry = None

        async def async_set_unique_id(self, uid):  # type: ignore[no-untyped-def]
            self._unique_id = uid

        def _abort_if_unique_id_configured(self):  # type: ignore[no-untyped-def]
            pass

        def _abort_if_unique_id_mismatch(self):  # type: ignore[no-untyped-def]
            pass

        def _get_reconfigure_entry(self):  # type: ignore[no-untyped-def]
            return getattr(self, "_reconfigure_entry", None)

        def async_create_entry(self, title, data, **kw):  # type: ignore[no-untyped-def]
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(self, step_id, data_schema=None, errors=None):  # type: ignore[no-untyped-def]
            return {"type": "form", "step_id": step_id, "errors": errors}

        def async_update_reload_and_abort(self, entry, data_updates=None):  # type: ignore[no-untyped-def]
            return {"type": "abort", "reason": "reconfigure_successful"}

        @staticmethod
        def async_get_options_flow(entry):  # type: ignore[no-untyped-def]
            return None

    class _FakeOptionsFlow:
        def __init_subclass__(cls, **kw):  # type: ignore[no-untyped-def]
            super().__init_subclass__(**kw)

        def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
            self.config_entry = None
            self.hass = None

        def add_suggested_values_to_schema(self, schema, options):  # type: ignore[no-untyped-def]
            return schema

        def async_create_entry(self, title, data):  # type: ignore[no-untyped-def]
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(self, step_id, data_schema=None, errors=None):  # type: ignore[no-untyped-def]
            return {"type": "form", "step_id": step_id, "errors": errors}

    # tolerate domain kw on subclasses
    class _FakeOptionsFlowWithReload(_FakeOptionsFlow):
        pass

    ha.config_entries = _make_fake_module(
        "homeassistant.config_entries",
        ConfigEntry=object,
        ConfigFlow=_FakeConfigFlow,
        ConfigFlowResult=dict,
        OptionsFlow=_FakeOptionsFlow,
        OptionsFlowWithReload=_FakeOptionsFlowWithReload,
    )

    class _Platform:
        BINARY_SENSOR = "binary_sensor"
        CLIMATE = "climate"
        SENSOR = "sensor"
        WATER_HEATER = "water_heater"

    # const
    class _EntityCategory:
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"

    class _UnitOfTemperature:
        CELSIUS = "°C"

    class _UnitOfTime:
        HOURS = "h"
        SECONDS = "s"

    ha.const = _make_fake_module(
        "homeassistant.const",
        Platform=_Platform,
        CONF_SCAN_INTERVAL="scan_interval",
        EntityCategory=_EntityCategory,
        UnitOfTemperature=_UnitOfTemperature,
        UnitOfTime=_UnitOfTime,
    )
    ha.exceptions = _make_fake_module(
        "homeassistant.exceptions",
        HomeAssistantError=Exception,
        ServiceValidationError=Exception,
    )
    ha.helpers = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = ha.helpers

    # helpers.update_coordinator
    class _FakeDataUpdateCoordinator:
        def __init__(self, hass, logger, name=None, config_entry=None, update_interval=None, always_update=None, **kw):  # type: ignore[no-untyped-def]
            self.hass = hass
            self.logger = logger
            self.name = name
            self.config_entry = config_entry
            self.update_interval = update_interval
            self.always_update = always_update
            self.data = None
            self._listeners = []

        async def async_config_entry_first_refresh(self):  # type: ignore[no-untyped-def]
            pass

        async def async_request_refresh(self):  # type: ignore[no-untyped-def]
            pass

        async def async_shutdown(self):  # type: ignore[no-untyped-def]
            pass

    class _FakeCoordinatorEntity:
        def __class_getitem__(cls, item):  # type: ignore[no-untyped-def]
            return cls

        def __init__(self, coordinator, *a, **kw):  # type: ignore[no-untyped-def]
            self.coordinator = coordinator

        @property
        def available(self):  # type: ignore[no-untyped-def]
            base = getattr(super(), "available", True)
            # super may not have available; just check coordinator data
            if hasattr(self.coordinator, "data"):
                return self.coordinator.data is not None and bool(base) if isinstance(base, bool) else self.coordinator.data is not None
            return True

    ha.helpers.update_coordinator = _make_fake_module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=_FakeDataUpdateCoordinator,
        CoordinatorEntity=_FakeCoordinatorEntity,
        UpdateFailed=Exception,
    )
    ha.helpers.device_registry = _make_fake_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=dict,
    )
    ha.helpers.entity_platform = _make_fake_module(
        "homeassistant.helpers.entity_platform",
        AddConfigEntryEntitiesCallback=object,
        AddEntitiesCallback=object,
    )
    ha.helpers.config_validation = _make_fake_module(
        "homeassistant.helpers.config_validation",
        string=str,
    )
    # compat: homeassistant.helpers.config_validation.string is used as validator; str works
    sys.modules["homeassistant.helpers.config_validation"].string = lambda x: str(x)

    # components package
    ha.components = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = ha.components

    # sensor
    class _SensorDeviceClass:
        TEMPERATURE = "temperature"
        ENUM = "enum"
        DURATION = "duration"

    class _SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class _FakeSensorEntity:
        pass

    from dataclasses import dataclass

    @dataclass(kw_only=True, frozen=True)
    class _SensorEntityDescription:
        key: str = ""
        translation_key: str | None = None
        device_class: object = None
        state_class: object = None
        native_unit_of_measurement: object = None
        suggested_display_precision: int | None = None
        entity_category: object = None
        entity_registry_enabled_default: bool = True
        options: list | None = None
        has_entity_name: bool = False

    sensor_mod = _make_fake_module(
        "homeassistant.components.sensor",
        SensorDeviceClass=_SensorDeviceClass,
        SensorEntity=_FakeSensorEntity,
        SensorEntityDescription=_SensorEntityDescription,
        SensorStateClass=_SensorStateClass,
    )

    # binary_sensor
    class _BinarySensorDeviceClass:
        RUNNING = "running"
        OPENING = "opening"
        PROBLEM = "problem"

    @dataclass(kw_only=True, frozen=True)
    class _BinarySensorEntityDescription:
        key: str = ""
        translation_key: str | None = None
        device_class: object = None
        entity_category: object = None
        has_entity_name: bool = False

    binary_mod = _make_fake_module(
        "homeassistant.components.binary_sensor",
        BinarySensorDeviceClass=_BinarySensorDeviceClass,
        BinarySensorEntity=object,
        BinarySensorEntityDescription=_BinarySensorEntityDescription,
    )

    # climate
    class _ClimateEntity:
        pass

    class _ClimateEntityFeature(int):
        def __new__(cls, v=0):  # type: ignore[no-untyped-def]
            obj = int.__new__(cls, v)
            obj._v = v  # type: ignore[attr-defined]
            return obj

        def __or__(self, other):  # type: ignore[no-untyped-def]
            return _ClimateEntityFeature(int(self) | int(other))

        def __and__(self, other):  # type: ignore[no-untyped-def]
            return _ClimateEntityFeature(int(self) & int(other))

    _ClimateEntityFeature.TARGET_TEMPERATURE = _ClimateEntityFeature(1)  # type: ignore[attr-defined]
    _ClimateEntityFeature.TURN_ON = _ClimateEntityFeature(2)  # type: ignore[attr-defined]
    _ClimateEntityFeature.TURN_OFF = _ClimateEntityFeature(4)  # type: ignore[attr-defined]
    _ClimateEntityFeature.PRESET_MODE = _ClimateEntityFeature(8)  # type: ignore[attr-defined]

    class _HVACAction:
        HEATING = "heating"
        IDLE = "idle"

    class _HVACMode:
        AUTO = "auto"
        OFF = "off"
        HEAT = "heat"

    _make_fake_module(
        "homeassistant.components.climate",
        ClimateEntity=_ClimateEntity,
        ClimateEntityFeature=_ClimateEntityFeature,
        HVACAction=_HVACAction,
        HVACMode=_HVACMode,
    )
    # water_heater
    class _WaterHeaterEntity:
        pass

    class _WaterHeaterEntityFeature(int):
        def __new__(cls, v=0):  # type: ignore[no-untyped-def]
            obj = int.__new__(cls, v)
            return obj

        def __or__(self, other):  # type: ignore[no-untyped-def]
            return _WaterHeaterEntityFeature(int(self) | int(other))

    _make_fake_module(
        "homeassistant.components.water_heater",
        STATE_ECO="eco",
        STATE_ELECTRIC="electric",
        STATE_HEAT_PUMP="heat_pump",
        STATE_OFF="off",
        STATE_PERFORMANCE="performance",
        WaterHeaterEntity=_WaterHeaterEntity,
        WaterHeaterEntityFeature=_WaterHeaterEntityFeature,
    )

    # serial
    serial_asyncio = _make_fake_module("serial_asyncio")
    serial_asyncio.open_serial_connection = MagicMock()
    serial = _make_fake_module("serial")
    serial.tools = types.ModuleType("serial.tools")
    sys.modules["serial.tools"] = serial.tools
    serial.tools.list_ports = _make_fake_module(
        "serial.tools.list_ports", comports=lambda: []
    )


_install_stubs()
