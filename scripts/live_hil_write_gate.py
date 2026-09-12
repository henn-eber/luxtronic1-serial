#!/usr/bin/env python3
"""Live HIL — Gate 2 guard: only allow writes after Gate 1 passed.

Gate 1 (``scripts/live_hil_readonly.py`` or
``tests/test_live_hil_readonly.py``) writes
``/tmp/live_hil_readonly_gate.json`` (or ``$LIVE_HIL_GATE_FILE``) with
``{"gate": 1, "result": "passed", ...}``.

This helper **refuses** to proceed unless that file exists, is recent
(``--max-age-h 24`` by default) and shows ``passed``. It is the single
entry point for any live write test — call it from a write script:

    python scripts/live_hil_write_gate.py --check
    # exit 0 == ok to write, exit 1 == blocked

    # Or as a guard inside a write script:
    from live_hil_write_gate import assert_gate_passed
    assert_gate_passed()

A write script should also set ``LIVE_HIL_ALLOW_WRITES=1`` and keep
``read_only=False`` on its client; the gate double-checks both the file
and the env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_GATE = Path(os.getenv("LIVE_HIL_GATE_FILE", "/tmp/live_hil_readonly_gate.json"))


def check_gate(gate_file: Path, max_age_h: float = 24.0) -> tuple[bool, str]:
    if not gate_file.exists():
        return False, f"Gate file {gate_file} missing — run Gate 1 readonly soak first (scripts/live_hil_readonly.py)"
    try:
        data = json.loads(gate_file.read_text())
    except Exception as e:
        return False, f"Gate file {gate_file} unreadable: {e}"
    if data.get("gate") != 1 or data.get("result") != "passed":
        return False, f"Gate file {gate_file} does not show passed: {data}"
    ts_str = data.get("ts")
    # Check freshness via mtime (more reliable than ts string)
    try:
        age_h = (time.time() - gate_file.stat().st_mtime) / 3600.0
    except Exception:
        age_h = 999
    if age_h > max_age_h:
        return False, f"Gate file {gate_file} is {age_h:.1f}h old (> {max_age_h}h) — re-run Gate 1"
    # Env guard: require explicit allow (prevents accidental write in a forgotten shell)
    if os.getenv("LIVE_HIL_ALLOW_WRITES") != "1":
        return False, "LIVE_HIL_ALLOW_WRITES != 1 — set LIVE_HIL_ALLOW_WRITES=1 to explicitly allow writes"
    return True, f"Gate 1 passed {gate_file} ({age_h:.1f}h ago) — writes allowed"


def assert_gate_passed(gate_file: Path | None = None, max_age_h: float = 24.0) -> None:
    gate_file = gate_file or DEFAULT_GATE
    ok, msg = check_gate(gate_file, max_age_h)
    if not ok:
        raise SystemExit(f"WRITE GATE BLOCKED: {msg}")


def main() -> None:
    p = argparse.ArgumentParser(description="Gate 2 write guard — checks Gate 1 passed")
    p.add_argument("--gate-file", default=str(DEFAULT_GATE), help="gate file from Gate 1")
    p.add_argument("--max-age-h", type=float, default=24.0, help="max age in hours before gate expires")
    p.add_argument("--check", action="store_true", help="just check and print result (exit 0/1)")
    args = p.parse_args()

    ok, msg = check_gate(Path(args.gate_file), args.max_age_h)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
