"""Async serial transport for Luxtronik 1.

A single persistent asyncio serial connection to the heat pump's RS232
service port (57600 8N1). All I/O is mediated through an ``asyncio.Lock``
so concurrent calls from the coordinator / write services cannot interleave.

The transport deliberately mirrors the ioBroker adapter's behaviour:

* one logical request at a time (``_lock``)
* each command sent as a single ``write``
* read responses assembled in ``_buffer`` until the framing test passes
* a hard chunk-count timeout destroys the connection and signals failure
* automatic reconnect with exponential back-off after any error
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from homeassistant.core import HomeAssistant

try:
    import serial_asyncio  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - pyserial-asyncio missing in dev env
    serial_asyncio = None  # type: ignore[assignment]

from .const import CRLF, DEFAULT_BAUDRATE, DEFAULT_BYTESIZE, DEFAULT_PARITY, DEFAULT_STOPBITS
from .protocol import FrameError, decode_line, line_terminator_993

_LOGGER = logging.getLogger(__name__)

# Safety limits
READ_TIMEOUT_S: float = 8.0  # wall clock per request
MAX_CHUNKS: int = 5  # chunks without a complete frame -> fail (matches ioBroker)
RECONNECT_INITIAL_S: float = 2.0
RECONNECT_MAX_S: float = 60.0


class LuxtronikConnectionError(Exception):
    """Raised when the transport cannot talk to the controller."""


@dataclass
class SerialConfig:
    """Connection settings for the serial transport."""

    url: str  # e.g. /dev/ttyUSB0 or COM3
    baudrate: int = DEFAULT_BAUDRATE
    bytesize: int = DEFAULT_BYTESIZE
    parity: str = DEFAULT_PARITY
    stopbits: int = DEFAULT_STOPBITS
    rtscts: bool = False
    xonxoff: bool = False


class LuxtronikTransport:
    """Owns the asyncio serial connection and provides ``query`` / ``execute_write``."""

    def __init__(self, hass: HomeAssistant, config: SerialConfig) -> None:
        self._hass = hass
        self._config = config
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._reconnect_delay = RECONNECT_INITIAL_S

    # ------------------------------------------------------------------ public

    @property
    def connected(self) -> bool:
        return self._connected

    async def async_connect(self) -> None:
        """Open the serial port (idempotent)."""

        if serial_asyncio is None:
            raise LuxtronikConnectionError(
                "pyserial-asyncio is not installed; "
                "run `pip install pyserial-asyncio` in the HA environment"
            )

        async with self._lock:
            if self._connected:
                return
            try:
                self._reader, self._writer = await serial_asyncio.open_serial_connection(
                    url=self._config.url,
                    baudrate=self._config.baudrate,
                    bytesize=self._config.bytesize,
                    parity=self._config.parity,
                    stopbits=self._config.stopbits,
                    rtscts=self._config.rtscts,
                    xonxoff=self._config.xonxoff,
                )
            except Exception as exc:
                raise LuxtronikConnectionError(
                    f"Failed to open {self._config.url}: {exc}"
                ) from exc
            self._connected = True
            self._reconnect_delay = RECONNECT_INITIAL_S
            _LOGGER.debug("Opened serial port %s @ %d%s%s",
                          self._config.url, self._config.baudrate,
                          self._config.parity, self._config.stopbits)

    async def async_close(self) -> None:
        """Close the port and release resources."""

        async with self._lock:
            await self._close_locked()

    async def query(self, command: str, expected_count: Optional[int] = None) -> list[bytes]:
        """Send a read command and return the raw CRLF-delimited lines.

        A read timeout triggers reconnect so the next request starts clean.
        """

        async with self._lock:
            await self._ensure_locked()
            return await self._query_locked(command, expected_count)

    async def execute_write(
        self,
        command: str,
        values: list[int],
        abort_token: Optional[asyncio.Event] = None,
    ) -> None:
        """Perform the 3-step write handshake: open / payload / 999."""

        async with self._lock:
            await self._ensure_locked()
            await self._execute_write_locked(command, values, abort_token)

    # ---------------------------------------------------------------- internal

    async def _ensure_locked(self) -> None:
        if self._connected and self._writer is not None and not self._writer.is_closing():
            return
        await self._close_locked()
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._config.url,
                baudrate=self._config.baudrate,
                bytesize=self._config.bytesize,
                parity=self._config.parity,
                stopbits=self._config.stopbits,
                rtscts=self._config.rtscts,
                xonxoff=self._config.xonxoff,
            )
            self._connected = True
        except Exception as exc:
            self._connected = False
            raise LuxtronikConnectionError(
                f"Serial reconnect to {self._config.url} failed: {exc}"
            ) from exc

    async def _close_locked(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # pragma: no cover - best-effort
                pass
        self._reader = None
        self._writer = None
        self._connected = False

    async def _query_locked(self, command: str, expected_count: Optional[int]) -> list[bytes]:
        assert self._writer is not None
        try:
            self._writer.write(f"{command}\r\n".encode("ascii"))
            await self._writer.drain()
        except Exception as exc:
            await self._close_locked()
            raise LuxtronikConnectionError(f"Write failed: {exc}") from exc

        return await self._read_until_complete(command, expected_count)

    async def _read_until_complete(
        self, command: str, expected_count: Optional[int]
    ) -> list[bytes]:
        assert self._reader is not None

        buffer = bytearray()
        deadline = asyncio.get_running_loop().time() + READ_TIMEOUT_S
        chunks = 0
        complete = False

        while asyncio.get_running_loop().time() < deadline:
            try:
                chunk = await asyncio.wait_for(self._reader.read(1024), timeout=2.0)
            except asyncio.TimeoutError:
                if complete:
                    break
                continue
            except Exception as exc:
                await self._close_locked()
                raise LuxtronikConnectionError(f"Read failed: {exc}") from exc

            if not chunk:
                break
            chunks += 1
            buffer.extend(chunk)

            lines = [ln for ln in buffer.split(CRLF) if ln]
            for raw in lines:
                try:
                    line = decode_line(raw)
                except FrameError:
                    continue
                if line.command != command:
                    continue
                if expected_count is not None and line.count != expected_count:
                    continue
                if len(line.values) >= line.count:
                    complete = True
                    break

            if complete:
                break
            if chunks > MAX_CHUNKS:
                break

        if not complete:
            await self._close_locked()
            raise LuxtronikConnectionError(
                f"Incomplete {command} response after {chunks} chunks"
            )

        return [bytes(ln) for ln in buffer.split(CRLF) if ln]

    async def _execute_write_locked(
        self,
        command: str,
        values: list[int],
        abort_token: Optional[asyncio.Event],
    ) -> None:
        assert self._writer is not None

        open_cmd = f"{command}\r\n".encode("ascii")
        payload = self._encode_payload(command, values)
        commit = b"999\r\n"
        cancel = self._encode_payload(command, [0])

        try:
            self._writer.write(open_cmd)
            await self._writer.drain()
        except Exception as exc:
            await self._close_locked()
            raise LuxtronikConnectionError(f"Write open failed: {exc}") from exc

        await asyncio.sleep(2.0)
        if abort_token is not None and abort_token.is_set():
            await self._abort_locked(cancel)
            return

        try:
            self._writer.write(payload)
            await self._writer.drain()
        except Exception as exc:
            await self._close_locked()
            raise LuxtronikConnectionError(f"Write payload failed: {exc}") from exc

        await asyncio.sleep(2.0)
        if abort_token is not None and abort_token.is_set():
            await self._abort_locked(cancel)
            return

        try:
            self._writer.write(commit)
            await self._writer.drain()
        except Exception as exc:
            await self._close_locked()
            raise LuxtronikConnectionError(f"Write commit failed: {exc}") from exc

        # Wait for the controller's "993\r\n999" handshake
        try:
            await self._await_commit(abort_token)
        except LuxtronikConnectionError:
            await self._abort_locked(cancel)
            raise

    async def _abort_locked(self, cancel_cmd: bytes) -> None:
        if self._writer is None or self._writer.is_closing():
            return
        try:
            self._writer.write(cancel_cmd)
            await self._writer.drain()
            await asyncio.sleep(0.2)
            self._writer.write(b"999\r\n")
            await self._writer.drain()
        except Exception:  # pragma: no cover - best-effort
            pass

    async def _await_commit(self, abort_token: Optional[asyncio.Event]) -> None:
        assert self._reader is not None
        buffer = bytearray()
        deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < deadline:
            if abort_token is not None and abort_token.is_set():
                raise LuxtronikConnectionError("aborted")
            try:
                chunk = await asyncio.wait_for(self._reader.read(256), timeout=1.0)
            except asyncio.TimeoutError:
                if line_terminator_993(bytes(buffer)):
                    return
                continue
            except Exception as exc:
                await self._close_locked()
                raise LuxtronikConnectionError(f"Read failed: {exc}") from exc
            if not chunk:
                break
            buffer.extend(chunk)
            if line_terminator_993(bytes(buffer)):
                return
        # Not fatal: some firmwares don't emit the close marker. ioBroker
        # treats this case as success too.

    @staticmethod
    def _encode_payload(command: str, values: list[int]) -> bytes:
        parts = [str(int(v)) for v in values]
        return f"{command};{len(parts)};{';'.join(parts)}\r\n".encode("ascii")