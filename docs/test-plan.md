# HA-Luxtronic1 Test & Validation Plan

## 0. Starting position (verified)
- Covered: `tests/test_protocol.py` — 13 tests over `protocol.py` + `models.py`,
  using stub HA modules in `tests/conftest.py`.
- Missing: `requirements-test.txt`, pytest/coverage config, CI workflow,
  coverage measurement.
- Blocker: dev env is Python 3.9; Home Assistant and its test harness
  require Python ≥3.12 (3.13 current).
- Sandbox: Ubuntu VM on PVE (8 vCPU / 12 GB, expandable), Docker not yet
  installed, opencode installed. USB-RS232 passthrough to the VM approved
  for live-test windows.

## 1. Phase 0 — VM base (~20 min, one-time, reusable)
1. Install Docker Engine from Docker's official Ubuntu repository plus the
   compose plugin; add the user to the `docker` group; verify with
   `docker run hello-world`.
2. Layout: `~/projects/ha-luxtronic1/` for this project. Future projects
   repeat the pattern (own container/venv each, nothing HA-specific on
   the host) so the VM stays reusable.
3. Resources are sufficient as-is; no increase needed (HA dev container
   wants ~4 GB, slim test container ~1 GB).

## 2. Phase 1 — Test harness (~1–2 h)
1. Add `requirements-test.txt`: `homeassistant==<pinned>`,
   `pytest-homeassistant-custom-component==<same version line>`,
   `pytest-cov`, `pyserial`, `pyserial-asyncio`. HA and PHACC must be
   pinned to the same version line — the most common setup failure.
2. Add `pyproject.toml`: `asyncio_mode = "auto"`, coverage target ≥95%.
3. Slim `python:3.13` container (or venv) with the repo mounted; retire
   the stub-`conftest.py` approach in favor of the real harness.
4. New tests (transport boundary mocked with canned wire frames):
   - `test_config_flow.py` — success, `cannot_connect`, duplicate abort,
     reconfigure, options (closes bronze `config-flow-test-coverage`);
   - `test_coordinator.py` — first-refresh `ConfigEntryNotReady` path,
     `UpdateFailed` on drops, `always_update=False` no-change behavior;
   - `test_sensor.py`, `test_binary_sensor.py`, `test_climate.py`,
     `test_water_heater.py` — states, `native_value`, `STATE_*`
     mappings, device-registry grouping;
   - `test_services.py` — all services incl. `ServiceValidationError`
     paths (CR/LF injection, bad `HH:MM`);
   - `test_diagnostics.py` — serial-path redaction
     (closes silver `test-coverage`).
5. GitHub Actions workflow: pytest + coverage, hassfest, HACS validation
   on push.

## 3. Phase 2 — Emulator HIL on the VM (~1 h)
`socat` PTY pair + fake-Luxtronik responder replaying
`1100/1800/2100/3200/3400/3405/3505`; full integration run end-to-end.
No hardware touched.

## 4. Phase 3 — Live HIL (~1 h, supervised)
1. PVE USB passthrough of the adapter to the Ubuntu VM (exclusive access —
   nothing else may hold the port during the window).
2. Config flow against the real `/dev/ttyUSBx`; `send_raw` per read
   command, diff values against the ioBroker reference.
3. Writes strictly ordered by risk, re-reading after each: DHW setpoint →
   modes → heating curve → hysteresis → schedule → clock.

## 5. Done criteria
- `pytest --cov` ≥95% green on Python 3.13
- hassfest + HACS actions clean
- Emulator run clean
- Live read parity confirmed, one low-risk write verified
