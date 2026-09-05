"""High-level async client for the Luxtronik 1 controller.

Wraps ``LuxtronikTransport`` with typed methods that parse the wire
response into dataclasses from ``models.py``.

The class is deliberately stateless beyond the transport reference: all
read-modify-write flows (e.g. ``set_heating_curve_offset``) read the
current block first so we never clobber an unknown trailing field.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .const import (
    CMD_BW_SCHEDULE,
    CMD_BW_SCHEDULE_WRITE,
    CMD_BW_SETPOINT_WRITE,
    CMD_HEATING_CURVE,
    CMD_HEATING_CURVE_WRITE,
    CMD_HEATING_MODE,
    CMD_HEATING_MODE_WRITE,
    CMD_HOTWATER_MODE,
    CMD_HOTWATER_MODE_WRITE,
    CMD_HYSTERESIS_WRITE,
    CMD_OVERVIEW,
    CMD_TEMP_SETTINGS,
    READ_COMMANDS,
    WRITE_COOLDOWN,
)
from .models import (
    BWSchedule,
    HeatingCurve,
    Overview,
    TempSettings,
)
from .protocol import decode_line
from .transport import LuxtronikConnectionError, LuxtronikTransport

_LOGGER = logging.getLogger(__name__)


class LuxtronikReadOnlyError(Exception):
    """Raised when a write is attempted while read-only mode is enabled."""


class LuxtronikClient:
    """Friendly, typed wrapper around the protocol transport."""

    def __init__(
        self, transport: LuxtronikTransport, read_only: bool = False
    ) -> None:
        self._transport = transport
        self._write_lock = asyncio.Lock()
        self._last_write: float = 0.0
        self._read_only = read_only

    @property
    def read_only(self) -> bool:
        """Return True if all writes to the controller are blocked."""
        return self._read_only

    @read_only.setter
    def read_only(self, value: bool) -> None:
        self._read_only = bool(value)

    def _ensure_writable(self) -> None:
        """Raise if read-only mode blocks writes to the controller."""
        if self._read_only:
            raise LuxtronikReadOnlyError(
                "Read-only mode is enabled: writing to the heat pump "
                "controller is blocked. Disable read-only mode in the "
                "integration options to allow writes."
            )

    # ----------------------------------------------------------------- reads

    async def read_overview(self) -> Overview:
        """``1800`` multi-line snapshot."""

        lines = await self._transport.query(CMD_OVERVIEW, expected_count=None)
        return Overview.from_lines(self._decode_lines(lines, fallback_count=22))

    async def read_heating_curve(self) -> HeatingCurve:
        """``3400`` heating-curve block."""

        lines = await self._transport.query(CMD_HEATING_CURVE, expected_count=9)
        values = self._decode_values(lines, CMD_HEATING_CURVE, expected_count=9)
        return HeatingCurve.from_values(values)

    async def read_temp_settings(self) -> TempSettings:
        """``2100`` temperature limits / hysteresis block."""

        lines = await self._transport.query(CMD_TEMP_SETTINGS, expected_count=16)
        values = self._decode_values(lines, CMD_TEMP_SETTINGS, expected_count=16)
        return TempSettings.from_values(values)

    async def read_bw_schedule(self) -> BWSchedule:
        """``3200`` DHW weekly time window."""

        lines = await self._transport.query(CMD_BW_SCHEDULE, expected_count=8)
        values = self._decode_values(lines, CMD_BW_SCHEDULE, expected_count=8)
        return BWSchedule.from_values(values)

    async def read_heating_mode(self) -> int:
        """``3405`` heating mode (0..5)."""

        lines = await self._transport.query(CMD_HEATING_MODE, expected_count=1)
        return self._decode_values(lines, CMD_HEATING_MODE, expected_count=1)[0]

    async def read_hotwater_mode(self) -> int:
        """``3505`` hot water mode (0..5)."""

        lines = await self._transport.query(CMD_HOTWATER_MODE, expected_count=1)
        return self._decode_values(lines, CMD_HOTWATER_MODE, expected_count=1)[0]

    # ---------------------------------------------------------------- writes

    async def set_dhw_setpoint(self, value_celsius: float) -> None:
        """Set the DHW target temperature (``3501``).

        ``value_celsius`` is converted to the wire scale (×10, rounded).
        """

        raw = int(round(value_celsius * 10))
        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            await self._transport.execute_write(CMD_BW_SETPOINT_WRITE, [raw])

    async def set_heating_mode(self, mode: int) -> None:
        """Set heating mode (``3406``). 0..5."""

        self._validate_mode(mode)
        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            await self._transport.execute_write(CMD_HEATING_MODE_WRITE, [mode])

    async def set_hotwater_mode(self, mode: int) -> None:
        """Set hot water mode (``3506``). 0..5."""

        self._validate_mode(mode)
        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            await self._transport.execute_write(CMD_HOTWATER_MODE_WRITE, [mode])

    async def set_bw_schedule(self, schedule: BWSchedule) -> None:
        """Write the weekly DHW schedule (``3201``)."""

        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            await self._transport.execute_write(
                CMD_BW_SCHEDULE_WRITE, schedule.to_wire()
            )

    async def set_heating_curve(
        self,
        *,
        offset: Optional[float] = None,
        endpoint: Optional[float] = None,
        parallel_shift: Optional[float] = None,
        night_setback: Optional[float] = None,
    ) -> None:
        """Mutate one or more heating-curve fields and write the full block back.

        All values are in °C; they are scaled ×10 before transmission. Any
        argument left as ``None`` keeps the current value.
        """

        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            curve = await self.read_heating_curve()
            if offset is not None:
                curve.offset = int(round(offset * 10))
            if endpoint is not None:
                curve.endpoint = int(round(endpoint * 10))
            if parallel_shift is not None:
                curve.parallel_shift = int(round(parallel_shift * 10))
            if night_setback is not None:
                curve.night_setback = int(round(night_setback * 10))
            await self._transport.execute_write(
                CMD_HEATING_CURVE_WRITE, curve.to_wire()
            )

    async def set_hysteresis(
        self,
        *,
        heating: Optional[float] = None,
        dhw: Optional[float] = None,
    ) -> None:
        """Mutate hysteresis fields and write the full block back."""

        self._ensure_writable()
        async with self._write_lock:
            await self._respect_cooldown()
            settings = await self.read_temp_settings()
            if heating is not None:
                settings.hysteresis_heating = int(round(heating * 10))
            if dhw is not None:
                settings.hysteresis_dhw = int(round(dhw * 10))
            await self._transport.execute_write(
                CMD_HYSTERESIS_WRITE, settings.to_wire()
            )

    # ---------------------------------------------------------------- helpers

    async def async_send_raw(self, command: str) -> list[bytes]:
        """Send a raw command (no length-prefix / framing checks).

        Returns the raw CRLF-delimited lines. Useful for the ``send_raw``
        service. In read-only mode only pure read commands (see
        ``READ_COMMANDS``) are allowed.
        """

        command = command.strip()
        base = command.split(";", 1)[0].strip()
        if self._read_only and base not in READ_COMMANDS:
            raise LuxtronikReadOnlyError(
                f"Read-only mode is enabled: raw command {base!r} may write "
                "to the controller and is blocked."
            )
        async with self._write_lock:
            await self._transport.query(command)

    async def _respect_cooldown(self) -> None:
        elapsed = asyncio.get_running_loop().time() - self._last_write
        if elapsed < WRITE_COOLDOWN:
            await asyncio.sleep(WRITE_COOLDOWN - elapsed)
        self._last_write = asyncio.get_running_loop().time()

    @staticmethod
    def _validate_mode(mode: int) -> None:
        if not 0 <= mode <= 5:
            raise ValueError(f"mode must be 0..5, got {mode}")

    @staticmethod
    def _decode_values(
        lines: list[bytes], command: str, expected_count: int
    ) -> list[int]:
        """Pick the matching command line and return its integer payload."""

        for raw in lines:
            try:
                line = decode_line(raw)
            except Exception:
                continue
            if line.command != command:
                continue
            if line.count != expected_count:
                continue
            return line.values
        raise LuxtronikConnectionError(
            f"No matching {command} line with count={expected_count} in response"
        )

    @staticmethod
    def _decode_lines(lines: list[bytes], fallback_count: int) -> list[str]:
        """Return CRLF-cleaned ASCII text lines."""

        out: list[str] = []
        for raw in lines:
            try:
                text = raw.decode("ascii").strip()
            except UnicodeDecodeError:
                continue
            if not text:
                continue
            out.append(text)
        # Pad to expected length when the controller emits fewer lines
        while len(out) < fallback_count:
            out.append("")
        return out