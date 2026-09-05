"""Frame encode/decode for the Luxtronik 1 text protocol.

Wire format reference (extracted from ioBroker ioBroker.luxtronik1 main.js):

* Outbound: ASCII command followed by CRLF, e.g. ``b"1100\\r\\n"``.
* Outbound writes use a 3-step handshake:
    T+0.0s:  <CMD>\\r\\n
    T+2.0s:  <CMD>;<count>;<v1>;<v2>;...\\r\\n
    T+4.0s:  999\\r\\n
* Inbound: one or more CRLF-terminated lines of ``;<CMD>;<count>;<values>``.
* A line is complete when ``len(parts) == count + 2``.
* The controller replies with ``993\\r\\n999`` to end a write session.
* The controller replies with ``779`` to signal a desynced command; the
  driver must abort by writing ``<CMD>;0\\r\\n`` followed by ``999\\r\\n``.

There is no checksum, no length-prefix and no escaping — every byte on the
wire is plain ASCII printable or CR/LF.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .const import CRLF

MAX_LINE_BYTES = 4096  # safety cap to discard runaway garbage


@dataclass
class ParsedLine:
    """A single decoded CRLF-terminated line."""

    command: str
    count: int
    values: list[int]

    @property
    def is_complete(self) -> bool:
        """Return True iff the line passes the ``count + 2`` length check."""

        return len(self.values) >= self.count


class FrameError(Exception):
    """Raised on malformed frames."""


def encode_command(command: str, values: Iterable[int] | None = None) -> bytes:
    """Encode a single CRLF-terminated command.

    Examples
    --------
    >>> encode_command("1100")
    b'1100\\r\\n'
    >>> encode_command("3406", [1])
    b'3406;1;1\\r\\n'
    """

    if not command:
        raise FrameError("empty command")
    if values is None:
        payload = command
    else:
        nums = [str(int(v)) for v in values]
        payload = f"{command};{len(nums)};" + ".".join(nums).replace(".", ";")
    return payload.encode("ascii") + CRLF


def decode_line(line: bytes) -> ParsedLine:
    """Decode a single CRLF-stripped line into a ``ParsedLine``.

    Raises
    ------
    FrameError
        If the line is empty, non-ASCII, missing the count field, or has a
        non-integer value.
    """

    if not line:
        raise FrameError("empty line")
    try:
        text = line.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise FrameError(f"non-ASCII line: {line!r}") from exc

    parts = text.split(";")
    if len(parts) < 2:
        raise FrameError(f"line too short: {text!r}")

    command = parts[0]
    try:
        count = int(parts[1])
    except ValueError as exc:
        raise FrameError(f"invalid count field in {text!r}") from exc

    values: list[int] = []
    for raw in parts[2:]:
        if not raw:
            continue
        try:
            values.append(int(raw))
        except ValueError as exc:
            raise FrameError(f"non-integer value {raw!r} in {text!r}") from exc

    return ParsedLine(command=command, count=count, values=values)


def has_complete_frame(buffer: bytes, command: str, expected_count: int | None = None) -> bool:
    """Return True if the buffer holds at least one complete line for ``command``.

    The check matches the ioBroker adapter's validation:
    ``buffer.includes(command)`` and ``len(parts) == count + 2``.

    For multi-line commands (1800) the caller scans line-by-line.
    """

    if command.encode("ascii") not in buffer:
        return False
    for raw in buffer.split(CRLF):
        if not raw:
            continue
        try:
            line = decode_line(raw)
        except FrameError:
            continue
        if line.command != command:
            continue
        if expected_count is not None and line.count != expected_count:
            continue
        if line.is_complete:
            return True
    return False


def line_terminator_993(buffer: bytes) -> bool:
    """Return True if the controller has emitted ``993\\r\\n999``."""

    return b"993\r\n999" in buffer