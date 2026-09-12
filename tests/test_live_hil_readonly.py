"""Live HIL — Gate 1: read-only soak (never writes).

This is the *extra-careful* layer requested before any write is ever
attempted against the real heat pump:

* **No writes are ever issued** — the client is locked to ``read_only=True``
  and the transport's ``execute_write`` is monkey-patched to hard-fail if
  called (second safety net beyond ``client.py:69 _ensure_writable``).
* Only ``READ_COMMANDS`` (1100/1800/2100/3200/3400/3405/3505) are exercised.
* The test is **skipped by default** — it runs only when you explicitly
  set ``LIVE_HIL=1`` and ``LIVE_SERIAL_PORT=/dev/ttyUSBx`` in the shell.
  This guarantees CI / emulator runs never touch hardware.
* On success it writes a gate file ``/tmp/live_hil_readonly_gate.json``
  (or ``$LIVE_HIL_GATE_FILE``) that the write-gate checks before allowing
  any write.

Usage (on the PVE VM with passed-through USB-RS232, exclusive access):

    # 1. Short smoke (20 cycles, default)
    LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 pytest tests/test_live_hil_readonly.py -v -s

    # 2. Longer soak (e.g. 120 cycles / ~10 min at default polling)
    LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 LIVE_HIL_CYCLES=120 pytest tests/test_live_hil_readonly.py -v -s

    # 3. Or via the standalone script (no pytest needed):
    python scripts/live_hil_readonly.py --port /dev/ttyUSB0 --cycles 60

Only if this gate passes without any ``779`` desync / timeout / write
attempt should you proceed to gate 2 (writes).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Skip entirely unless operator explicitly enables live HIL.
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_HIL") != "1" or not os.getenv("LIVE_SERIAL_PORT"),
    reason="Live HIL readonly gate: set LIVE_HIL=1 and LIVE_SERIAL_PORT=/dev/ttyUSBx to run against real hardware",
)

from luxtronic1.transport import LuxtronikTransport, SerialConfig  # noqa: E402
from luxtronic1.client import LuxtronikClient, LuxtronikReadOnlyError  # noqa: E402
from luxtronic1.const import READ_COMMANDS  # noqa: E402


GATE_FILE = Path(os.getenv("LIVE_HIL_GATE_FILE", "/tmp/live_hil_readonly_gate.json"))


def _gate_already_failed(*, cycles: int, errors: list[str]) -> Path:
    payload = {
        "gate": 1,
        "phase": "readonly_soak",
        "result": "failed",
        "port": os.getenv("LIVE_SERIAL_PORT"),
        "cycles_requested": cycles,
        "errors": errors,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    GATE_FILE.write_text(json.dumps(payload, indent=2))
    return GATE_FILE


def _gate_passed(*, cycles: int, elapsed_s: float, overview_sample: dict) -> Path:
    payload = {
        "gate": 1,
        "phase": "readonly_soak",
        "result": "passed",
        "port": os.getenv("LIVE_SERIAL_PORT"),
        "cycles_requested": cycles,
        "elapsed_s": round(elapsed_s, 2),
        "overview_sample": overview_sample,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    GATE_FILE.write_text(json.dumps(payload, indent=2))
    return GATE_FILE


@pytest.mark.asyncio
async def test_live_hil_readonly_gate():
    port = os.getenv("LIVE_SERIAL_PORT")
    assert port, "LIVE_SERIAL_PORT must be set (e.g. /dev/ttyUSB0)"
    cycles = int(os.getenv("LIVE_HIL_CYCLES", "20"))
    assert cycles > 0

    hass = MagicMock()
    cfg = SerialConfig(url=port, baudrate=57600, parity="N", stopbits=1)
    transport = LuxtronikTransport(hass, cfg)
    client = LuxtronikClient(transport, read_only=True)
    assert client.read_only is True

    # Hard guard: fail the test if *any* write is attempted (covers
    # client.py:69 + async_send_raw + future direct transport calls).
    original_execute = transport.execute_write

    async def _guarded_execute(*args, **kwargs):
        raise AssertionError(
            "Gate 1 is read-only — execute_write must never be called. "
            f"Blocked args={args} kwargs={kwargs}. Check that LIVE_HIL_ALLOW_WRITES is not set."
        )

    transport.execute_write = _guarded_execute  # type: ignore[method-assign]

    # Also guard async_send_raw: only READ_COMMANDS may pass in read-only.
    original_send_raw = client.async_send_raw

    async def _guarded_send_raw(cmd: str, *a, **kw):
        base = cmd.strip().split(";", 1)[0].strip()
        assert base in READ_COMMANDS, f"Gate 1 blocked non-read raw command {base!r} — only {sorted(READ_COMMANDS)} allowed"
        return await original_send_raw(cmd, *a, **kw)

    client.async_send_raw = _guarded_send_raw  # type: ignore[method-assign]

    # Optional extra: forbid transport.query with a non-read command
    original_query = transport.query

    async def _guarded_query(cmd: str, *a, **kw):
        base = cmd.strip().split(";", 1)[0].strip()
        assert base in READ_COMMANDS, f"Gate 1 blocked non-read query {base!r}"
        return await original_query(cmd, *a, **kw)

    transport.query = _guarded_query  # type: ignore[method-assign]

    t0 = time.monotonic()
    errors: list[str] = []
    last_overview = None

    try:
        for i in range(cycles):
            try:
                ov = await client.read_overview()
                last_overview = {
                    "flow": ov.temperatures.flow,
                    "outdoor": ov.temperatures.outdoor,
                    "wp_type": ov.status.wp_type,
                    "software_version": ov.status.software_version,
                    "cycle": i,
                }
                # Exercise each read individually (covers all READ_COMMANDS)
                await client.read_heating_mode()
                await client.read_hotwater_mode()
                await client.read_heating_curve()
                await client.read_temp_settings()
                await client.read_bw_schedule()
                # Raw reads for each command (still read-only)
                for cmd in sorted(READ_COMMANDS):
                    lines = await client.async_send_raw(cmd)
                    assert any(cmd.encode() in l for l in lines), f"no {cmd} in raw response"
            except LuxtronikReadOnlyError as e:
                pytest.fail(f"Read-only gate incorrectly raised LuxtronikReadOnlyError on read: {e}")
            except AssertionError:
                raise
            except Exception as e:
                errors.append(f"cycle {i}: {type(e).__name__}: {e}")
                # Do not hammer the controller on failure — brief pause
                import asyncio

                await asyncio.sleep(1.0)
                # Re-raise if too many consecutive failures
                if len(errors) >= 3 and i < cycles - 1:
                    # Keep collecting but surface at end
                    pass

            # Small inter-cycle gap to mimic real polling (avoid tight loop)
            if i < cycles - 1:
                import asyncio

                await asyncio.sleep(float(os.getenv("LIVE_HIL_INTERVAL_S", "2.0")))

        elapsed = time.monotonic() - t0

        if errors:
            _gate_already_failed(cycles=cycles, errors=errors)
            pytest.fail(
                f"Gate 1 readonly soak failed after {cycles} cycles ({elapsed:.1f}s): "
                f"{errors[:5]} — gate file {GATE_FILE} written. Fix port / wiring before writes."
            )

        _gate_passed(cycles=cycles, elapsed_s=elapsed, overview_sample=last_overview or {})
        # Sanity: ensure no writes slipped through
        assert not hasattr(transport, "_writes")  # transport never tracks writes; guard is our mock

    finally:
        # Restore for clean teardown (transport close will be called by coordinator/client if needed)
        transport.execute_write = original_execute  # type: ignore[method-assign]
        try:
            await transport.async_close()
        except Exception:
            pass
