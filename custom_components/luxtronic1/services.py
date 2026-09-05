"""Home Assistant services exposed by the Luxtronik 1 integration.

The ``luxtronic1.send_raw`` service lets users send any ASCII command to
the heat pump and see the response in the log — invaluable for exploring
undocumented commands on a specific firmware.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .client import LuxtronikReadOnlyError
from .const import DOMAIN
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_RAW = "send_raw"
SERVICE_SET_HEATING_CURVE = "set_heating_curve"
SERVICE_SET_HYSTERESIS = "set_hysteresis"
SERVICE_SET_BW_SCHEDULE = "set_bw_schedule"

ATTR_COMMAND = "command"
ATTR_HEATING_OFFSET = "heating_offset"
ATTR_HEATING_ENDPOINT = "heating_endpoint"
ATTR_HEATING_PARALLEL = "heating_parallel"
ATTR_NIGHT_SETBACK = "night_setback"
ATTR_HYST_HEATING = "hysteresis_heating"
ATTR_HYST_DHW = "hysteresis_dhw"
ATTR_START1 = "start1"
ATTR_END1 = "end1"
ATTR_START2 = "start2"
ATTR_END2 = "end2"

SEND_RAW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
    }
)

SET_HEATING_CURVE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_HEATING_OFFSET): vol.Coerce(float),
        vol.Optional(ATTR_HEATING_ENDPOINT): vol.Coerce(float),
        vol.Optional(ATTR_HEATING_PARALLEL): vol.Coerce(float),
        vol.Optional(ATTR_NIGHT_SETBACK): vol.Coerce(float),
    }
)

SET_HYSTERESIS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_HYST_HEATING): vol.Coerce(float),
        vol.Optional(ATTR_HYST_DHW): vol.Coerce(float),
    }
)

SET_BW_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START1): cv.string,
        vol.Required(ATTR_END1): cv.string,
        vol.Optional(ATTR_START2): cv.string,
        vol.Optional(ATTR_END2): cv.string,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register the Luxtronik 1 services (idempotent)."""

    if hass.services.has_service(DOMAIN, SERVICE_SEND_RAW):
        return

    def _resolve_coordinator(call: ServiceCall) -> LuxtronikCoordinator:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("No Luxtronik 1 integration is configured")
        coordinator = entries[0].runtime_data
        if coordinator is None:
            raise HomeAssistantError("Luxtronik 1 integration is not ready yet")
        return coordinator

    def _ensure_writable(coordinator: LuxtronikCoordinator) -> None:
        if coordinator.read_only:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="read_only_mode",
            )

    async def send_raw(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(call)
        cmd = call.data[ATTR_COMMAND]
        if "\n" in cmd or "\r" in cmd:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="command_contains_newline",
            )
        try:
            lines = await coordinator.client.async_send_raw(cmd)
        except LuxtronikReadOnlyError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="read_only_mode",
            ) from exc
        except Exception as exc:
            raise HomeAssistantError(f"send_raw failed: {exc}") from exc
        _LOGGER.info("luxtronic1.send_raw(%s) -> %r", cmd, lines)

    async def set_heating_curve(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(call)
        _ensure_writable(coordinator)
        try:
            await coordinator.client.set_heating_curve(
                offset=call.data.get(ATTR_HEATING_OFFSET),
                endpoint=call.data.get(ATTR_HEATING_ENDPOINT),
                parallel_shift=call.data.get(ATTR_HEATING_PARALLEL),
                night_setback=call.data.get(ATTR_NIGHT_SETBACK),
            )
        except Exception as exc:
            raise HomeAssistantError(f"set_heating_curve failed: {exc}") from exc
        await coordinator.async_request_refresh()

    async def set_hysteresis(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(call)
        _ensure_writable(coordinator)
        try:
            await coordinator.client.set_hysteresis(
                heating=call.data.get(ATTR_HYST_HEATING),
                dhw=call.data.get(ATTR_HYST_DHW),
            )
        except Exception as exc:
            raise HomeAssistantError(f"set_hysteresis failed: {exc}") from exc
        await coordinator.async_request_refresh()

    async def set_bw_schedule(call: ServiceCall) -> None:
        from .models import BWSchedule

        coordinator = _resolve_coordinator(call)
        _ensure_writable(coordinator)

        def _parse(value: str) -> tuple[int, int]:
            try:
                hour_s, minute_s = value.split(":", 1)
                hour, minute = int(hour_s), int(minute_s)
            except ValueError as exc:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_time_format",
                    translation_placeholders={"value": value},
                ) from exc
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_time_format",
                    translation_placeholders={"value": value},
                )
            return hour, minute

        start1_h, start1_m = _parse(call.data[ATTR_START1])
        end1_h, end1_m = _parse(call.data[ATTR_END1])
        start2 = call.data.get(ATTR_START2, "00:00")
        end2 = call.data.get(ATTR_END2, "00:00")
        start2_h, start2_m = _parse(start2)
        end2_h, end2_m = _parse(end2)

        try:
            await coordinator.client.set_bw_schedule(
                BWSchedule(
                    start1_h=start1_h, start1_m=start1_m,
                    end1_h=end1_h, end1_m=end1_m,
                    start2_h=start2_h, start2_m=start2_m,
                    end2_h=end2_h, end2_m=end2_m,
                )
            )
        except Exception as exc:
            raise HomeAssistantError(f"set_bw_schedule failed: {exc}") from exc
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_RAW, send_raw, schema=SEND_RAW_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HEATING_CURVE,
        set_heating_curve,
        schema=SET_HEATING_CURVE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_HYSTERESIS, set_hysteresis, schema=SET_HYSTERESIS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BW_SCHEDULE, set_bw_schedule, schema=SET_BW_SCHEDULE_SCHEMA
    )