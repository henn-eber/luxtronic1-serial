"""Tests for read-only mode (strict read/write separation)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow `python -m pytest` from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components"))

import pytest  # noqa: E402

from luxtronic1.client import (  # noqa: E402
    LuxtronikClient,
    LuxtronikReadOnlyError,
)
from luxtronic1.models import BWSchedule  # noqa: E402


class _FakeTransport:
    """Minimal transport double recording all calls."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.writes: list[tuple[str, list[int]]] = []

    async def query(self, command, expected_count=None):  # noqa: ANN001, ANN202
        self.queries.append(command)
        if command == "3400":
            return [b"3400;9;0;0;0;0;0;0;0;0;0"]
        if command == "2100":
            return [b"2100;16;" + b";".join([b"0"] * 16)]
        return [b"3405;1;0"]

    async def execute_write(self, command, values):  # noqa: ANN001, ANN202
        self.writes.append((command, list(values)))


def test_all_writes_blocked_when_read_only() -> None:
    async def _main() -> None:
        client = LuxtronikClient(object(), read_only=True)  # type: ignore[arg-type]
        assert client.read_only is True

        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_dhw_setpoint(50.0)
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_heating_mode(0)
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_hotwater_mode(0)
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_bw_schedule(BWSchedule())
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_heating_curve(offset=1.0)
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_hysteresis(heating=1.0)

    asyncio.run(_main())


def test_send_raw_allows_reads_in_read_only_mode() -> None:
    async def _main() -> None:
        transport = _FakeTransport()
        client = LuxtronikClient(transport, read_only=True)  # type: ignore[arg-type]

        expected = ["1100", "1800", "2100", "3200", "3400", "3405", "3505"]
        for cmd in expected:
            await client.async_send_raw(cmd)

        assert transport.queries == expected
        assert transport.writes == []

    asyncio.run(_main())


def test_send_raw_blocks_writes_in_read_only_mode() -> None:
    async def _main() -> None:
        transport = _FakeTransport()
        client = LuxtronikClient(transport, read_only=True)  # type: ignore[arg-type]

        for cmd in ("3501;1;500", "3406;1;0", "999", "3401"):
            with pytest.raises(LuxtronikReadOnlyError):
                await client.async_send_raw(cmd)

        assert transport.queries == []
        assert transport.writes == []

    asyncio.run(_main())


def test_writes_allowed_when_not_read_only() -> None:
    async def _main() -> None:
        transport = _FakeTransport()
        client = LuxtronikClient(transport, read_only=False)  # type: ignore[arg-type]

        await client.set_heating_mode(0)
        await client.set_dhw_setpoint(50.0)
        await client.set_heating_curve(offset=1.0)

        assert ("3406", [0]) in transport.writes
        assert ("3501", [500]) in transport.writes
        assert any(cmd == "3401" for cmd, _ in transport.writes)

    asyncio.run(_main())


def test_read_only_flag_is_mutable() -> None:
    async def _main() -> None:
        client = LuxtronikClient(object())  # type: ignore[arg-type]
        assert client.read_only is False
        client.read_only = True
        assert client.read_only is True
        with pytest.raises(LuxtronikReadOnlyError):
            await client.set_heating_mode(0)

    asyncio.run(_main())
