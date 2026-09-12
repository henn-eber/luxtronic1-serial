# HA-Luxtronic1 Test & Validation Plan

## 0. Starting position (verified 2025-09-12)
- Covered: `tests/test_protocol.py` — 13 tests over `protocol.py` + `models.py`; expanded to **101 tests / 100% coverage** (`pyproject.toml:27` `fail_under=95`, `custom_components/luxtronic1` branch coverage).
- CI: **green** `actions/runs/34680972515` — `hassfest`/`hacs`/`pytest`/`emulator` all `success` on `ubuntu-latest` + `setup-python@v5` `python 3.13`.
- Env: Python **3.13.5** (`.venv` + CI `3.13`), **Docker 29.8.0** installed/verified, Node runner **24** (GitHub default). `socat` not required in CI.
- Harness: lightweight stub `tests/conftest.py:24` **retained intentionally** (see §1) — no `homeassistant`/`pytest-homeassistant-custom-component` pinning.
- HACS/hassfest: `hacs.json:1` minimal, `custom_components/luxtronic1/brand/icon.png` placeholder, `manifest.json:1` sorted keys, `__init__.py:14` `CONFIG_SCHEMA = cv.config_entry_only_config_schema`.
- Emulator: `tests/emulator/fake_luxtronik.py:155` `pty.openpty()` + `FakeLuxtronik` replaying `1100/1800/2100/3200/3400/3405/3505`; `scripts/emulator.sh:1` `socat` only as manual fallback.
- Sandbox: Ubuntu VM on PVE (8 vCPU / 12 GB, expandable), USB-RS232 passthrough approved for live-test windows (exclusive access during window).

## 1. Phase 0 — VM base (already provisioned — verify only)
1. Verify Docker: `docker run hello-world` (29.8.0+). Compose plugin optional.
2. Layout: repo at `luxtronic1-serial/` (was `~/projects/ha-luxtronic1/` in draft) — each future project keeps own venv/container, nothing HA-specific on host.
3. Verify Python 3.13: `.venv` or `python:3.13` container, `pip install -r requirements-test.txt`.
4. Resources sufficient as-is; HA dev container ~4 GB, slim test container ~1 GB.

## 2. Phase 1 — Test harness (implemented — stub retained intentionally)
1. `requirements-test.txt:1`: `pytest==9.1.1`, `pytest-cov==7.1.0`, `pytest-asyncio==1.4.0`, `pyserial==3.5`, `pyserial-asyncio==0.6`, `voluptuous==0.15.2`. **No** `homeassistant==<pinned>` / `pytest-homeassistant-custom-component` — avoids version-line pinning fragility. Trade-off: stub does not exercise real HA entity registry; see stub vs PHACC decision below.
2. `pyproject.toml:10`: `asyncio_mode="auto"`, `tool.coverage` `source=["custom_components/luxtronic1"]`, `fail_under=95` (actual **100%**, `1190` statements).
3. `tests/conftest.py:24` `_install_stubs()` retained intentionally — fakes `homeassistant.core/config_entries/const/helpers.update_coordinator/helpers.config_validation/components.sensor|binary_sensor|climate|water_heater/serial_asyncio`. Real harness not needed for `hassfest`/`HACS` (validated via Docker `ghcr.io/home-assistant/hassfest` / `ghcr.io/hacs/action:main`). Stub extended `conftest.py:194` with `config_entry_only_config_schema = vol.Schema({})` to support `__init__.py:14`.
4. Tests — intent-based coverage (actual files, not draft names):
   - config-flow / reconfigure / options / duplicate abort — `tests/test_*.py` (`test_779_and_preset.py`, `test_readonly.py`, `test_boost.py`) + `tests/test_fix2_coverage.py:1` (15 tests covering `client.py:253`/`climate.py:101`/`water_heater.py:95`/`protocol.py:127`/`models.py:324`/`config_flow.py:151`/`transport.py:214`);
   - coordinator: `ConfigEntryNotReady` first-refresh, `UpdateFailed` on drops, `always_update=False`;
   - sensor/binary_sensor/climate/water_heater: states, `native_value`, `STATE_*` mappings, device grouping;
   - services incl. `ServiceValidationError` paths (CR/LF injection, bad `HH:MM`);
   - diagnostics: serial-path redaction;
   - transport framing/boundary: `tests/test_transport_extra.py` + `tests/test_protocol.py` (canned wire frames). CI `pytest` job `.github/workflows/ci.yaml:25` runs `python -m pytest --cov --cov-fail-under=95 -v --tb=long`.
5. GitHub Actions `.github/workflows/ci.yaml:1`: `push`/`pull_request` on `main` → `hassfest` (`checkout@v5` + `home-assistant/actions/hassfest@master`), `hacs` (`hacs/action@main` `category: integration` `ignore: brands topics`), `pytest` (`setup-python@v5` `3.13` + `pip install -r requirements-test.txt`), `emulator` (`tests/test_emulator_hil.py`). Node-24 runner: `checkout@v5` is Node 24; `setup-python@v5` still targets Node 20 → informational warning forced onto Node 24 (fix by bumping to `setup-python@v6` when available, non-blocking).

> Stub vs `pytest-homeassistant-custom-component`: stub is fast/no pinning; PHACC (`homeassistant==pinned` + `pytest-homeassistant-custom-component` same line, `Python ≥3.12`) gives real `hass` fixture/entity registry for full HA fidelity. Kept stub because CI/hassfest/coverage goals are met; migrate only if bronze `config-flow-test-coverage` / silver `test-coverage` needs real HA state machine. See repo decision log.

## 3. Phase 2 — Emulator HIL on the VM (implemented)
- **PTY-native** (not `socat`-dependent): `tests/emulator/fake_luxtronik.py:57` `CANNED` + `OVERVIEW_LINES:31` 22-line `1800` block (`1400;29` zeros, `2100;16`), `FakeLuxtronik._run:91` async responder, `create_pty_pair:155` via `pty.openpty()`. Write handshake `…;payload` → `999` → `993\r\n999`.
- `tests/test_emulator_hil.py:1` 3 tests with `real_serial_transport:78` bypassing `conftest.py:326` `MagicMock` stubs via `_load_real_serial():29` (real `serial.serial_for_url`); verified locally `pytest tests/test_emulator_hil.py -v` `3 passed` and in Docker `python:3.13` / `ubuntu:22.04` + CI `emulator` job `.github/workflows/ci.yaml:53`.
- `scripts/emulator.sh:1` provides manual `socat pty,raw,echo=0,link=/tmp/ttyV0 ↔ /tmp/ttyV1` fallback; automated CI uses Python PTY so `socat` not installed on VM is fine.
- No hardware touched.

## 4. Phase 3 — Live HIL (~1 h, supervised — next)
1. PVE USB passthrough of the adapter to the Ubuntu VM (exclusive access — nothing else may hold the port during the window).
2. Config flow against the real `/dev/ttyUSBx`; `send_raw` per read command (`READ_COMMANDS` in `const.py:44`, `57600 8N1` via `pyserial`), diff values against the ioBroker reference.
3. Writes strictly ordered by risk, re-reading after each: DHW setpoint → modes → heating curve → hysteresis → schedule → clock.

## 5. Done criteria
- `pytest --cov` ≥95% green on Python 3.13 — **met: 100% / 101 passed** (`python -m pytest --cov=custom_components/luxtronic1 --cov-report=term-missing --cov-fail-under=95`)
- hassfest + HACS actions clean — **met: `hassfest: success` `Invalid integrations: 0`, `hacs: success`**
- Emulator run clean — **met: `pytest tests/test_emulator_hil.py -v --tb=short` `3 passed` in CI and Docker**
- Live read parity confirmed, one low-risk write verified — **pending Phase 3**
