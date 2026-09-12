#!/usr/bin/env bash
# Phase 2 — Emulator HIL on the VM
# Starts a socat PTY pair + fake Luxtronik responder for manual testing.
# Usage:
#   ./scripts/emulator.sh          # creates /tmp/ttyV0 <-> /tmp/ttyV1, runs fake on V1
#   # in another terminal:
#   python3 -c "from tests.emulator.fake_luxtronik import CANNED; print(CANNED)"
#   pytest tests/test_emulator_hil.py -v
#
# Requires: socat (apt install socat), python3 with pyserial-asyncio
set -euo pipefail

V0=/tmp/ttyV0
V1=/tmp/ttyV1

if ! command -v socat >/dev/null 2>&1; then
  echo "socat not found — falling back to Python PTY (see tests/emulator/fake_luxtronik.py:create_pty_pair)"
  echo "Run: python -m pytest tests/test_emulator_hil.py -v"
  exit 0
fi

echo "Creating PTY pair $V0 <-> $V1 via socat..."
rm -f "$V0" "$V1"
socat -d -d pty,raw,echo=0,link="$V0" pty,raw,echo=0,link="$V1" &
SOCAT_PID=$!
sleep 0.5

if [[ ! -e "$V0" || ! -e "$V1" ]]; then
  echo "Failed to create PTY pair"
  kill $SOCAT_PID || true
  exit 1
fi

echo "PTY ready: $V0 (for integration) <-> $V1 (for fake)"
echo "Starting FakeLuxtronik on $V1 (Ctrl+C to stop)..."
# Run fake responder in foreground on V1 master (use python helper)
python3 -c "
import asyncio, os
import pty
from tests.emulator.fake_luxtronik import FakeLuxtronik

# Open V1 as master fd via socat symlink — we need to open the PTY slave side directly
# Socat's PTY pair: V0 and V1 are symlinks to /dev/pts/N. Open V1 for reading/writing.
import pathlib, os
# Find master fd by opening V1
fd = os.open('$V1', os.O_RDWR | os.O_NOCTTY)
print(f'Fake on fd {fd} -> $V1')
fake = FakeLuxtronik(fd)
async def main():
    await fake.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await fake.stop()
asyncio.run(main())
"
# Cleanup
kill $SOCAT_PID || true
rm -f "$V0" "$V1"
