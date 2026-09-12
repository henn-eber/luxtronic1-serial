"""Phase 2 — Emulator HIL on the VM.

Uses a PTY pair + FakeLuxtronik responder (no hardware touched).
Automated version uses pty.openpty() + FakeLuxtronik for CI.
No conftest stubs — real serial_asyncio is used directly (PHACC harness).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.emulator.fake_luxtronik import FakeLuxtronik, create_pty_pair
from luxtronic1.transport import LuxtronikTransport, SerialConfig
from luxtronic1.client import LuxtronikClient
from luxtronic1.coordinator import LuxtronikCoordinator


@pytest.mark.asyncio
async def test_emulator_overview_parity():
    master_fd, slave_path = create_pty_pair()
    fake = FakeLuxtronik(master_fd)
    await fake.start()
    try:
        hass = MagicMock()
        cfg = SerialConfig(url=slave_path, baudrate=57600, parity="N", stopbits=1)
        transport = LuxtronikTransport(hass, cfg)
        client = LuxtronikClient(transport, read_only=False)

        # Raw reads — parity vs canned values
        ov = await client.read_overview()
        assert ov.temperatures.flow == 310
        assert ov.temperatures.outdoor == 45
        assert ov.status.wp_type == "LWPM"
        assert ov.status.software_version == "1.44"

        assert await client.read_heating_mode() == 0
        assert await client.read_hotwater_mode() == 0
        assert (await client.read_heating_curve()).endpoint == 320
        assert (await client.read_temp_settings()).return_limit == 300
        bw = await client.read_bw_schedule()
        assert bw.start1_h == 5 and bw.start1_m == 30

        # Raw send_raw for each READ_COMMANDS
        for cmd in ["1100", "2100", "3200", "3400", "3405", "3505"]:
            lines = await client.async_send_raw(cmd)
            assert any(cmd.encode() in l for l in lines)

    finally:
        await fake.stop()
        try:
            os.close(master_fd)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_emulator_coordinator_full_update():
    master_fd, slave_path = create_pty_pair()
    fake = FakeLuxtronik(master_fd)
    await fake.start()
    try:
        hass = MagicMock()
        entry = MagicMock()
        entry.data = {"serial_port": slave_path, "baudrate": 57600, "parity": "N", "stopbits": 1}
        entry.options = {"scan_interval": 300, "read_only": False}
        entry.entry_id = "test"
        coord = LuxtronikCoordinator(hass, entry)
        data = await coord._async_update_data()
        assert "overview" in data
        assert "heating_mode" in data
        assert data["overview"].temperatures.flow == 310
        await coord.async_shutdown()
    finally:
        await fake.stop()
        try:
            os.close(master_fd)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_emulator_write_handshake():
    master_fd, slave_path = create_pty_pair()
    fake = FakeLuxtronik(master_fd)
    await fake.start()
    try:
        hass = MagicMock()
        cfg = SerialConfig(url=slave_path)
        transport = LuxtronikTransport(hass, cfg)
        client = LuxtronikClient(transport, read_only=False)
        # Patch cooldown and transport sleeps to avoid 2s delays
        client._last_write = 0
        import luxtronic1.client as client_mod
        from unittest.mock import patch as _patch

        orig = client_mod.WRITE_COOLDOWN
        client_mod.WRITE_COOLDOWN = 0
        try:
            with _patch("asyncio.sleep", new=AsyncMock()):
                await client.set_dhw_setpoint(45.0)
                await client.set_heating_mode(1)
                await client.set_hotwater_mode(1)
            # Verify transport still usable for reads after writes (restore sleep for reads)
            assert await client.read_heating_mode() == 0
        finally:
            client_mod.WRITE_COOLDOWN = orig
    finally:
        await fake.stop()
        try:
            os.close(master_fd)
        except OSError:
            pass
