#!/usr/bin/env python3
"""Live HIL — Gate 1: read-only soak against the real Luxtronik 1.

This standalone script does the same read-only soak as
``tests/test_live_hil_readonly.py`` but without pytest — useful for a
quick manual check from the PVE VM shell.

It **never issues a write**:

* client is created with ``read_only=True``
* ``transport.execute_write`` is replaced with a hard-failing stub
* only ``READ_COMMANDS`` (1100/1800/2100/3200/3400/3405/3505) are queried
* result is written to ``/tmp/live_hil_readonly_gate.json`` (or
  ``$LIVE_HIL_GATE_FILE``) — the write-gate checks this file before any
  write is allowed.

Usage:
    python scripts/live_hil_readonly.py --port /dev/ttyUSB0 --cycles 30 --interval 2.0
    # or with env:
    LIVE_SERIAL_PORT=/dev/ttyUSB0 python scripts/live_hil_readonly.py

Exit code 0 == gate passed, 1 == failed (see gate file).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

# Ensure repo root on path when run as `python scripts/...`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from luxtronic1.transport import LuxtronikTransport, SerialConfig
from luxtronic1.client import LuxtronikClient
from luxtronic1.const import READ_COMMANDS


async def _run(port: str, cycles: int, interval: float, gate_file: Path) -> int:
    hass = MagicMock()
    cfg = SerialConfig(url=port, baudrate=57600, parity="N", stopbits=1)
    transport = LuxtronikTransport(hass, cfg)
    client = LuxtronikClient(transport, read_only=True)

    original_execute = transport.execute_write

    async def _guarded_execute(*a, **kw):
        raise AssertionError("Gate 1 read-only: execute_write blocked")

    transport.execute_write = _guarded_execute  # type: ignore[method-assign]

    t0 = time.monotonic()
    errors: list[str] = []
    last_sample: dict = {}

    for i in range(cycles):
        try:
            ov = await client.read_overview()
            last_sample = {
                "flow": ov.temperatures.flow,
                "outdoor": ov.temperatures.outdoor,
                "wp_type": ov.status.wp_type,
                "software": ov.status.software_version,
                "cycle": i,
            }
            print(f"[{i+1}/{cycles}] overview ok: flow={ov.temperatures.flow} outdoor={ov.temperatures.outdoor} {ov.status.wp_type} {ov.status.software_version}", flush=True)
            await client.read_heating_mode()
            await client.read_hotwater_mode()
            await client.read_heating_curve()
            await client.read_temp_settings()
            await client.read_bw_schedule()
            for cmd in sorted(READ_COMMANDS):
                lines = await client.async_send_raw(cmd)
                if not any(cmd.encode() in l for l in lines):
                    raise RuntimeError(f"command {cmd} not in raw response")
        except Exception as e:
            msg = f"cycle {i}: {type(e).__name__}: {e}"
            print(f"  !! {msg}", file=sys.stderr, flush=True)
            errors.append(msg)
            await asyncio.sleep(1.0)

        if i < cycles - 1:
            await asyncio.sleep(interval)

    elapsed = time.monotonic() - t0

    if errors:
        payload = {
            "gate": 1,
            "phase": "readonly_soak",
            "result": "failed",
            "port": port,
            "cycles_requested": cycles,
            "errors": errors,
            "elapsed_s": round(elapsed, 2),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        gate_file.write_text(json.dumps(payload, indent=2))
        print(f"\nGate 1 FAILED — {len(errors)} errors, gate file {gate_file}", file=sys.stderr)
        try:
            await transport.async_close()
        except Exception:
            pass
        return 1

    payload = {
        "gate": 1,
        "phase": "readonly_soak",
        "result": "passed",
        "port": port,
        "cycles_requested": cycles,
        "elapsed_s": round(elapsed, 2),
        "overview_sample": last_sample,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    gate_file.write_text(json.dumps(payload, indent=2))
    print(f"\nGate 1 PASSED — {cycles} cycles in {elapsed:.1f}s, gate file {gate_file}")
    try:
        await transport.async_close()
    except Exception:
        pass
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Live HIL Gate 1: read-only soak (no writes)")
    p.add_argument("--port", default=os.getenv("LIVE_SERIAL_PORT", "/dev/ttyUSB0"), help="serial port (default: $LIVE_SERIAL_PORT or /dev/ttyUSB0)")
    p.add_argument("--cycles", type=int, default=int(os.getenv("LIVE_HIL_CYCLES", "30")), help="number of read cycles")
    p.add_argument("--interval", type=float, default=float(os.getenv("LIVE_HIL_INTERVAL_S", "2.0")), help="seconds between cycles")
    p.add_argument("--gate-file", default=os.getenv("LIVE_HIL_GATE_FILE", "/tmp/live_hil_readonly_gate.json"), help="gate file written on success/failure")
    args = p.parse_args()

    rc = asyncio.run(_run(args.port, args.cycles, args.interval, Path(args.gate_file)))
    sys.exit(rc)


if __name__ == "__main__":
    main()
