# Live HIL — Two-Gate Safety Procedure

This is the **extra-careful** procedure you asked for before any write ever
touches the real heat pump. Gate 1 is *read-only forever* — only if it
passes completely do we open Gate 2 for writes.

> **Invariant:** No live test / script may call
``LuxtronikTransport.execute_write`` unless Gate 1 has passed within
``24h`` **and** ``LIVE_HIL_ALLOW_WRITES=1`` is set.

## Gates

| Gate | What it does | Writes? | How to run | Pass condition | Gate file |
|------|--------------|---------|------------|----------------|-----------|
| 1 | Read-only soak — exercises every ``READ_COMMANDS`` (`1100`/`1800`/`2100`/`3200`/`3400`/`3405`/`3505`) repeatedly, checks for ``779`` desync / timeouts | **Never** — ``read_only=True`` + hard guard that fails if ``execute_write`` is called | ``LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 pytest tests/test_live_hil_readonly.py -v -s`` or ``python scripts/live_hil_readonly.py --port /dev/ttyUSB0 --cycles 30`` | All cycles read ok, no ``779``, gate file ``result: passed`` | ``/tmp/live_hil_readonly_gate.json`` (or ``$LIVE_HIL_GATE_FILE``) |
| 2 | Writes, ordered by risk — DHW setpoint → modes → heating curve → hysteresis → schedule → clock, re-reading after each | Only if gate 1 ``passed`` `<24h` + ``LIVE_HIL_ALLOW_WRITES=1`` | ``LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 LIVE_HIL_ALLOW_WRITES=1 python scripts/live_hil_write_gate.py --check`` then your write test | Each write followed by read-back matches | — |

## Gate 1 — Read-Only Soak (run this first, always)

On the PVE VM with the USB-RS232 passed through **exclusively** (nothing else
holding ``/dev/ttyUSB0``):

```bash
# Quick smoke (20 cycles, default, ~40s)
LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 pytest tests/test_live_hil_readonly.py -v -s

# Longer soak (60 cycles, ~2 min at 2s interval)
LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 LIVE_HIL_CYCLES=60 pytest tests/test_live_hil_readonly.py -v -s

# Or without pytest:
python scripts/live_hil_readonly.py --port /dev/ttyUSB0 --cycles 60 --interval 2.0
cat /tmp/live_hil_readonly_gate.json
```

What it checks:

* ``LuxtronikClient(read_only=True)`` — ``client.py:69 _ensure_writable`` would
  raise ``LuxtronikReadOnlyError`` on any write.
* Second guard: ``transport.execute_write`` is replaced with a stub that
  ``raise AssertionError(… read-only …)`` — even a direct transport call fails.
* Third guard: ``transport.query`` and ``client.async_send_raw`` assert
  ``base in READ_COMMANDS`` (`const.py:44`).
* Each cycle reads ``overview`` + all 6 individual reads + raw ``READ_COMMANDS``
  and asserts the command is in the response.

If any cycle fails (timeout, ``779`` desync, or blocked write attempt) the
test writes ``{"result": "failed", "errors": […]}`` to the gate file and
``pytest.fail()``s — **do not proceed to writes**.

Without ``LIVE_HIL=1`` the test is `skipped` (`pytestmark.skipif`) so CI /
emulator runs (`docker compose run --rm test`, GitHub ``pytest``) never
touch hardware.

## Gate 2 — Writes (only after Gate 1 passed)

Gate 2 is blocked by ``scripts/live_hil_write_gate.py``:

```bash
# This will exit 1 and print why, until Gate 1 has passed:
python scripts/live_hil_write_gate.py --check

# After Gate 1 passed (within 24h):
LIVE_HIL_ALLOW_WRITES=1 python scripts/live_hil_write_gate.py --check
# -> "Gate 1 passed /tmp/live_hil_readonly_gate.json (0.3h ago) — writes allowed"
```

A write script **must** call at its top:

```python
from live_hil_write_gate import assert_gate_passed
assert_gate_passed()  # exits with "WRITE GATE BLOCKED" unless Gate 1 passed
# also:
assert os.getenv("LIVE_HIL_ALLOW_WRITES") == "1"
client = LuxtronikClient(transport, read_only=False)  # still respects coordinator options
```

Ordered write checklist (re-read after each, keep ``READ_ONLY`` `False`
only for this window — re-enable read-only via integration options after):

1. DHW setpoint ``3501`` (lowest risk, easily reversible)
2. Modes ``3406``/``3506`` (AUTO → … → back)
3. Heating curve ``3401`` (offset/endpoint …)
4. Hysteresis ``2101``
5. BW schedule ``3201`` (``HH:MM`` validated, ``ServiceValidationError`` on bad format)
6. Clock (if implemented)

Each step: ``read_*`` → capture → ``set_*`` → sleep ``WRITE_COOLDOWN`` `5.0`s
(`const.py:35`) → ``read_*`` → diff vs pre-read. Any step that
returns ``779`` triggers ``0;0``+``999`` abort (`transport.py:342`) and
reconnect — log it and stop.

## Safety Checklist Before Any Live Run

* [ ] Gate 1 soak passed within 24h (`cat /tmp/live_hil_readonly_gate.json` shows ``"result": "passed"``)
* [ ] ``LIVE_HIL_ALLOW_WRITES=1`` is set in the same shell (otherwise Gate 2 refuses)
* [ ] Exclusive port access verified (`lsof /dev/ttyUSB0` shows only your process)
* [ ] Have the ioBroker reference values to diff against (or a photo of the controller display)
* [ ] Know how to revert: re-apply previous value immediately after each write
