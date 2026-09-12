"""Phase 2 — Emulator HIL on the VM.

Uses a PTY pair + FakeLuxtronik responder (no hardware touched).
Covers socat PTY fallback: if socat is available the test can be run
manually via scripts/emulator.sh, but the automated version uses
pty.openpty() + FakeLuxtronik for CI.

Note: conftest.py stubs serial_asyncio with MagicMock. These tests need
the real pyserial-asyncio, so we temporarily restore it.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.emulator.fake_luxtronik import FakeLuxtronik, create_pty_pair
from luxtronic1.transport import SerialConfig, LuxtronikTransport
from luxtronic1.client import LuxtronikClient
from luxtronic1.coordinator import LuxtronikCoordinator


def _load_real_serial():
    """Load real serial and serial_asyncio, bypassing conftest stubs."""
    import pathlib

    # Save fakes
    fakes = {}
    for name in ["serial", "serial.tools", "serial.tools.list_ports", "serial_asyncio"]:
        if name in sys.modules:
            mod = sys.modules[name]
            # Detect stub by missing serial_for_url or MagicMock
            is_stub = False
            if name == "serial" and not hasattr(mod, "serial_for_url"):
                is_stub = True
            if name == "serial_asyncio" and hasattr(mod, "open_serial_connection") and isinstance(mod.open_serial_connection, MagicMock):
                is_stub = True
            if is_stub:
                fakes[name] = mod
                del sys.modules[name]
    reals = {}
    try:
        # Force re-import from site-packages
        for name in ["serial", "serial_asyncio"]:
            spec = importlib.util.find_spec(name)
            if spec is None:
                # fallback search in venv
                candidates = list(pathlib.Path(".venv").rglob(f"{name.replace('.', '/')}/__init__.py"))
                if not candidates:
                    candidates = list(pathlib.Path(sys.prefix).rglob(f"{name.replace('.', '/')}/__init__.py"))
                if candidates:
                    spec = importlib.util.spec_from_file_location(name, str(candidates[0]))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                spec.loader.exec_module(mod)  # type: ignore
                reals[name] = mod
        # Ensure serial.tools.list_ports is real
        if "serial.tools.list_ports" in fakes:
            # re-import will populate it
            try:
                import serial.tools.list_ports as real_lp

                reals["serial.tools.list_ports"] = real_lp
            except Exception:
                pass
        return reals.get("serial_asyncio"), fakes
    except Exception:
        return None, fakes


@contextmanager
def real_serial_transport():
    import luxtronic1.transport as tr_mod

    orig_sa = tr_mod.serial_asyncio
    real_sa, fakes = _load_real_serial()
    if real_sa is None:
        yield
        return
    tr_mod.serial_asyncio = real_sa
    try:
        yield
    finally:
        tr_mod.serial_asyncio = orig_sa
        # Restore fakes for other tests
        for name, mod in fakes.items():
            sys.modules[name] = mod
        # Also restore serial.tools chain if needed
        try:
            import serial  # real

            # If conftest's serial stub was saved, ensure its tools still mocked for other tests
            # Other tests patch serial.tools.list_ports.comports, so we need to keep stub's behavior
            # Re-install stub's list_ports if it was faked
            if "serial.tools.list_ports" in fakes:
                sys.modules["serial.tools.list_ports"] = fakes["serial.tools.list_ports"]
        except Exception:
            pass


@pytest.mark.asyncio
async def test_emulator_overview_parity():
    master_fd, slave_path = create_pty_pair()
    fake = FakeLuxtronik(master_fd)
    await fake.start()
    try:
        with real_serial_transport():
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
        with real_serial_transport():
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
        with real_serial_transport():
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
