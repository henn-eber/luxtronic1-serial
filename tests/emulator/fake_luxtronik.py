"""Fake Luxtronik 1 responder for PTY-based HIL.

Listens on a PTY master fd and replays canned wire frames for
1100/1800/2100/3200/3400/3405/3505. Write handshake (open / payload / 999)
is accepted and answered with 993\\r\\n999.

The responder is deliberately simple: it reads CRLF-terminated ASCII lines
and writes back CRLF-terminated responses. It mirrors the ioBroker adapter's
field layout so Overview.from_lines parses correctly.
"""
from __future__ import annotations

import asyncio
import os
from typing import Dict, List

CRLF = b"\r\n"

# Canned single-line responses (command;count;values)
CANNED: Dict[str, bytes] = {
    "1100": b"1100;12;310;280;300;850;45;520;500;120;80;350;320;50\r\n",
    "2100": b"2100;16;300;20;50;10;10;70;500;10;350;100;50;700;50;20;450;0\r\n",
    "3200": b"3200;8;5;30;7;0;18;15;22;0\r\n",
    "3400": b"3400;9;10;320;0;20;0;0;0;0;0\r\n",
    "3405": b"3405;1;0\r\n",
    "3505": b"3505;1;0\r\n",
}

# 1800 multi-line block — 22 CRLF lines where indices match Overview.from_lines
# [2]=1100 temps, [3]=1200 inputs, [4]=1300 outputs, [5]=1400 runtimes, [6]=hours, [8..12] errors, [15..19] shutdowns, [21]=2900 status
OVERVIEW_LINES: List[bytes] = [
    b"1800;1;0\r\n",  # line 0 — 1800 header to satisfy has_complete_frame
    b"1800;1;0\r\n",  # line 1 — padding
    b"1100;12;310;280;300;850;45;520;500;120;80;350;320;50\r\n",  # 2 temps
    b"1200;6;0;1;0;1;0;0\r\n",  # 3 inputs (evu=1,mot=1)
    b"1300;13;0;1;0;1;0;0;0;1;1;0;0;0;0\r\n",  # 4 outputs (compressor_1=1, brine=1)
    b"1400;29;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0\r\n",  # 5 runtimes - 29 zeros
    b"1600;9;100;5;20;50;3;10;10;5;5000\r\n",  # 6 hours
    b"0000;0;\r\n",  # 7 padding
    b"701;1;2;20;10;0;0\r\n" if False else b"err;11;1;1;20;0;0;0\r\n",  # 8 error no-error
    b"err;11;1;1;20;0;0;0\r\n",  # 9
    b"err;11;1;1;20;0;0;0\r\n",  # 10
    b"err;11;1;1;20;0;0;0\r\n",  # 11
    b"err;11;1;1;20;0;0;0\r\n",  # 12
    b"0000;0;\r\n",  # 13
    b"0000;0;\r\n",  # 14
    b"shut;11;0;0;0;0;0;0\r\n",  # 15 shutdown no-error
    b"shut;11;0;0;0;0;0;0\r\n",  # 16
    b"shut;11;0;0;0;0;0;0\r\n",  # 17
    b"shut;11;0;0;0;0;0;0\r\n",  # 18
    b"shut;11;0;0;0;0;0;0\r\n",  # 19
    b"0000;0;\r\n",  # 20
    b"2900;4;LWPM;1.44;0;0\r\n",  # 21 status
]


def _response_for(cmd: str) -> List[bytes]:
    """Return canned response lines for a bare command."""
    base = cmd.split(";", 1)[0].strip()
    if base == "1800":
        return list(OVERVIEW_LINES)
    if base in CANNED:
        return [CANNED[base]]
    # Unknown read -> echo empty count 0
    if base.isdigit():
        return [f"{base};0;\r\n".encode()]
    return [b""]


class FakeLuxtronik:
    """Async PTY responder."""

    def __init__(self, master_fd: int):
        self.master_fd = master_fd
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        buf = bytearray()
        # Use a thread-pool reader for the blocking PTY fd
        while self._running:
            try:
                # Read with timeout to allow cancellation
                chunk = await loop.run_in_executor(None, self._read_chunk)
            except Exception:
                await asyncio.sleep(0.05)
                continue
            if not chunk:
                await asyncio.sleep(0.02)
                continue
            buf.extend(chunk)
            while CRLF in buf:
                idx = buf.find(CRLF)
                line = bytes(buf[:idx])
                del buf[: idx + len(CRLF)]
                if not line:
                    continue
                text = line.decode(errors="ignore").strip()
                if not text:
                    continue
                # Write commands: payload contains ';' and multiple values, or 999 commit
                if text == "999":
                    # commit -> answer 993/999
                    os.write(self.master_fd, b"993\r\n999\r\n")
                    continue
                # Handle write handshake payload: e.g. "3401;9;..." — ack silently, wait for 999
                if ";" in text:
                    base = text.split(";", 1)[0]
                    # If payload for a write (count>0 and not a pure read), don't answer yet — wait for 999
                    # Heuristic: if base is a write command (3401,2101,3201,3406,3501,3506) -> no immediate reply
                    if base in {"3401", "2101", "3201", "3406", "3501", "3506", "3201"}:
                        continue
                    # For unknown semicolon payload, ignore
                    if base.isdigit():
                        # Could be a read with extra payload — treat as read
                        resp = _response_for(base)
                        for r in resp:
                            os.write(self.master_fd, r)
                    continue
                # Bare read command
                resp = _response_for(text)
                for r in resp:
                    try:
                        os.write(self.master_fd, r)
                    except OSError:
                        break

    def _read_chunk(self) -> bytes:
        try:
            # non-blocking read with small timeout via os.read
            import select

            r, _, _ = select.select([self.master_fd], [], [], 0.1)
            if not r:
                return b""
            return os.read(self.master_fd, 1024)
        except OSError:
            return b""


def create_pty_pair() -> tuple[int, str]:
    """Create a PTY pair; returns (master_fd, slave_path)."""
    import pty

    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    # Keep slave_fd open until caller closes; we dup it so the PTY stays alive
    # via the path. Close the fd we opened — the device node remains.
    os.close(slave_fd)
    return master_fd, slave_path
