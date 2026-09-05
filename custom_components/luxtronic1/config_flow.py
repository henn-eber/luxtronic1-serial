"""Config flow for Luxtronik 1 Heat Pump."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from serial.tools import list_ports

from .client import LuxtronikClient
from .const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_PARITY,
    DEFAULT_READ_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DOMAIN,
)
from .transport import LuxtronikConnectionError, LuxtronikTransport, SerialConfig


def _list_serial_ports() -> list[str]:
    return [p.device for p in sorted(list_ports.comports(), key=lambda x: x.device)]


async def _async_test_connection(data: dict[str, Any]) -> None:
    config = SerialConfig(
        url=data[CONF_SERIAL_PORT],
        baudrate=int(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
        bytesize=DEFAULT_BYTESIZE,
        parity=data.get(CONF_PARITY, DEFAULT_PARITY),
        stopbits=int(data.get(CONF_STOPBITS, DEFAULT_STOPBITS)),
    )
    transport = LuxtronikTransport(None, config)  # type: ignore[arg-type]
    client = LuxtronikClient(transport)
    try:
        await transport.async_connect()
        await client.read_heating_mode()
    finally:
        await transport.async_close()


class LuxtronikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        ports = _list_serial_ports()

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SERIAL_PORT])
            self._abort_if_unique_id_configured()
            try:
                await _async_test_connection(user_input)
            except LuxtronikConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Luxtronik 1 ({user_input[CONF_SERIAL_PORT]})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): vol.In(ports) if ports else str,
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(
                    [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
                ),
                vol.Optional(CONF_PARITY, default=DEFAULT_PARITY): vol.In(
                    ["N", "E", "O"]
                ),
                vol.Optional(CONF_STOPBITS, default=DEFAULT_STOPBITS): vol.In([1, 2]),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the serial port of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SERIAL_PORT])
            self._abort_if_unique_id_mismatch()
            try:
                await _async_test_connection(user_input)
            except LuxtronikConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )

        ports = _list_serial_ports()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SERIAL_PORT,
                    default=entry.data.get(CONF_SERIAL_PORT),
                ): vol.In(ports) if ports else str,
                vol.Optional(
                    CONF_BAUDRATE,
                    default=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
                ): vol.In([1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]),
                vol.Optional(
                    CONF_PARITY,
                    default=entry.data.get(CONF_PARITY, DEFAULT_PARITY),
                ): vol.In(["N", "E", "O"]),
                vol.Optional(
                    CONF_STOPBITS,
                    default=entry.data.get(CONF_STOPBITS, DEFAULT_STOPBITS),
                ): vol.In([1, 2]),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowWithReload:
        return LuxtronikOptionsFlow()


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=30, max=3600)
        ),
        vol.Optional(CONF_READ_ONLY, default=DEFAULT_READ_ONLY): bool,
    }
)


class LuxtronikOptionsFlow(OptionsFlowWithReload):
    """Edit scan interval after setup (reloads the entry automatically)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )