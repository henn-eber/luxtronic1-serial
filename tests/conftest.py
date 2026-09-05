"""Pytest configuration.

The Luxtronik 1 integration imports Home Assistant at module load time,
which we don't have in this dev environment. We inject lightweight stub
modules so we can import the package and test the protocol / models
layers without a full HA install.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


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
    homeassistant = _make_fake_module("homeassistant")
    homeassistant.core = _make_fake_module(
        "homeassistant.core",
        HomeAssistant=object(),
        ServiceCall=object,
    )

    class _ConfigEntries:  # pragma: no cover - placeholder
        pass

    homeassistant.config_entries = _make_fake_module(
        "homeassistant.config_entries",
        ConfigEntry=object,
        ConfigFlow=object,
        ConfigFlowResult=dict,
        OptionsFlow=object,
        OptionsFlowWithReload=object,
    )

    class _Platform:  # pragma: no cover - placeholder
        BINARY_SENSOR = "binary_sensor"
        CLIMATE = "climate"
        SENSOR = "sensor"
        WATER_HEATER = "water_heater"

    homeassistant.const = _make_fake_module(
        "homeassistant.const",
        Platform=_Platform,
        CONF_SCAN_INTERVAL="scan_interval",
        EntityCategory=object,
        UnitOfTemperature=object,
        UnitOfTime=object,
    )
    homeassistant.exceptions = _make_fake_module(
        "homeassistant.exceptions",
        HomeAssistantError=Exception,
        ServiceValidationError=Exception,
    )
    homeassistant.helpers = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = homeassistant.helpers
    homeassistant.helpers.update_coordinator = _make_fake_module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=object,
        UpdateFailed=Exception,
    )
    homeassistant.helpers.device_registry = _make_fake_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=dict,
    )
    homeassistant.helpers.entity_platform = _make_fake_module(
        "homeassistant.helpers.entity_platform",
        AddConfigEntryEntitiesCallback=object,
        AddEntitiesCallback=object,
    )
    homeassistant.helpers.config_validation = _make_fake_module(
        "homeassistant.helpers.config_validation",
        string=str,
    )

    # The transport module imports pyserial_asyncio at module scope; provide
    # a stub so the package can be imported in the test environment.
    serial_asyncio = _make_fake_module("serial_asyncio")
    serial_asyncio.open_serial_connection = None  # not used in unit tests
    serial = _make_fake_module("serial")
    serial.tools = types.ModuleType("serial.tools")
    sys.modules["serial.tools"] = serial.tools
    serial.tools.list_ports = _make_fake_module(
        "serial.tools.list_ports", comports=lambda: []
    )


_install_stubs()