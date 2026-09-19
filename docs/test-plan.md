# HA-Luxtronic1 Test & Validation Plan

## 0. Starting position (verified 2026-09-19)
- Covered: `tests/test_protocol.py` — 13 tests → **101 tests / 100% coverage** (`pyproject.toml:27` `fail_under=95`, `custom_components/luxtronic1` branch coverage `1190` stmts, run `7a17d8c` + `AIT-logo-rs232.png`).
- CI: **green** `actions/runs/34684299605`+ → `hassfest`/`hacs`/`pytest`/`emulator` all `success` on `ubuntu-latest` + `setup-python@v7` `python 3.14` + `checkout@v7` (Node 24, no warnings).
- Env: Python **3.14.7** (`python:3.14-slim` `docker-compose.yml:3`, CI `3.14`, host `.venv` was `3.13.5` — now requires `3.14.2+` for `homeassistant==2026.9.1`), **Docker 29.8.0** + **Compose 5.5.1**, Node runner **24**.
- Harness: **PHACC** `pytest-homeassistant-custom-component==0.13.364` pinned to `homeassistant==2026.9.1` (`requirements-test.txt:1`, `const.py: MAJOR 2026.9.1` in PHACC). Replaces former `tests/conftest.py:24` `_install_stubs()` lightweight fakes; new `tests/conftest.py:1` is `pytest_plugins="pytest_homeassistant_custom_component"` + `auto_enable_custom_integrations` with `custom_components`+`ROOT` on `sys.path` for `tests/test_emulator_hil.py:23`.
- HACS/hassfest: `hacs.json:5` `homeassistant 2026.9.1`, `manifest.json:12` `version 0.1.0` `quality_scale gold`, `custom_components/luxtronic1/icon.png:256×256` + `logo.png:512×512` from `AIT-logo-rs232.png:1`, `hassfest 0 invalid`.
- Emulator: `tests/emulator/fake_luxtronik.py:155` `pty.openpty()` + `FakeLuxtronik` replaying `1100/1800/2100/3200/3400/3405/3505`; `scripts/emulator.sh:1` `socat` manual fallback, CI uses PTY. Adapted for PHACC: `real_serial_transport` removed (real `serial_asyncio` directly).
- Sandbox: Ubuntu VM on PVE (8 vCPU / 12 GB), USB-RS232 passthrough approved (exclusive).

## 1. Phase 0 — VM base (already provisioned — verify only)
1. Verify Docker 29.8.0+ / Compose 5.5.1+: `docker run hello-world`, `docker compose version`.
2. Layout: repo `luxtronic1-serial/` — `docker-compose.yml:1` defines `test`/`test-emulator`/`shell` (`python:3.14-slim`).
3. Verify Python 3.14: `docker compose run --rm test bash -c "python --version"` (`3.14.7`) or local `python3.14 -m pip install -r requirements-test.txt`.
4. Resources sufficient (HA 2026.9.1 wants ~4 GB for dev container, slim test ~1 GB).

## 2. Phase 1 — Test harness (migrated to PHACC 2026.9.1)
1. `requirements-test.txt:1`: `homeassistant==2026.9.1`, `pytest-homeassistant-custom-component==0.13.364`, `pyserial==3.5`, `pyserial-asyncio==0.6`. PHACC brings `pytest==9.0.3`, `pytest-cov==7.1.0`, `pytest-asyncio==1.4.0`, `voluptuous` etc. — **Python floor `>=3.14.2`** enforced by HA 2026.9.1 (`pypi`).
2. `pyproject.toml:10`: `asyncio_mode="auto"`, `asyncio_default_fixture_loop_scope="function"` (PHACC requirement), `tool.coverage` `source=["custom_components/luxtronic1"]`, `fail_under=95` (actual **100%**, `171` covered after `test_boost.py:863` fix for `OptionsFlow.config_entry` property).
3. `tests/conftest.py:1` — removed `336` lines of `_make_fake_module` / `FakeDataUpdateCoordinator` etc.; now minimal PHACC harness. `tests/test_boost.py:863` `test_options_flow` updated to mock `hass.config_entries.async_get_known_entry` + `handler=DOMAIN` / `_config_entry_id` because real `OptionsFlow.config_entry` is read-only property `config_entries.py:4009`.
4. Tests — all `7` modules (`test_protocol.py`, `test_boost.py`, `test_fix2_coverage.py`, `test_transport_extra.py`, `test_readonly.py`, `test_emulator_hil.py`, `test_779_and_preset.py`) run under real `hass` fixture where needed; protocol/transport still use canned frames, coordinator/sensor/binary/climate/water_heater use real `CoordinatorEntity`. One `RuntimeWarning` fixed via `coro.close()` in `test_fix2_coverage.py:43`.
5. `docker-compose.yml:1`: local dev via `docker compose run --rm test` (`pytest --cov --cov-fail-under=95`) and `test-emulator`. CI mirrors this in `.github/workflows/ci.yaml:25` `pytest` + `emulator` jobs (`checkout@v7`, `setup-python@v7` `3.14`).
6. GitHub Actions `.github/workflows/ci.yaml:1`: `push`/`pull_request` on `main` → `hassfest` (`checkout@v7` + `home-assistant/actions/hassfest@master` `composite` Docker), `hacs` (`hacs/action@main` `docker` `ghcr.io/hacs/action:main` `ignore: brands topics`), `pytest`/`emulator` (`setup-python@v7` `3.14`). Node-24 done (`checkout@v5→v7`, `setup-python@v5→v7` `6.0.0/7.0.0` `using: node24`), plus `release.yaml:1` `tag v*.*.*` → `hassfest` + `zip` + `gh-release`.

> Migration note: stub vs PHACC — stub was `Python 3.13`, no HA pin, `101/100%` but did not exercise real `DataUpdateCoordinator`/`ConfigEntry`. PHACC is `Python 3.14`, pinned HA 2026.9.1, real `hass` fixture — same `101/100%` but with HA fidelity; trade-off is larger install (~300 deps) and `3.14` floor. Decision: stay on PHACC for HIL-phase.

## 3. Phase 2 — Emulator HIL on the VM (implemented, PHACC-adapted)
- **PTY-native**: `tests/emulator/fake_luxtronik.py:57` `CANNED` + `OVERVIEW_LINES:31` `22`-line `1800` block, `FakeLuxtronik._run:91`, `create_pty_pair:155` `pty.openpty()`. Handshake `…;payload` → `999` → `993\r\n999`.
- `tests/test_emulator_hil.py:1` `3` tests — now import `tests.emulator.fake_luxtronik` via `ROOT` on `sys.path` (`tests/conftest.py:9`) and use real `serial_asyncio` (no `MagicMock` stub). Verified `docker compose run --rm test` `101 passed` incl. emulator, and CI `emulator` `success`.
- `scripts/emulator.sh:1` manual `socat` fallback retained; CI uses Python PTY ( `socat` not installed on VM still fine).
- No hardware touched.

## 4. Phase 3 — Live HIL (~1 h, supervised — next) — two-gate
1. **Gate 1 read-only soak** (`docs/live-hil.md:1`): `LIVE_HIL=1 LIVE_SERIAL_PORT=/dev/ttyUSB0 pytest tests/test_live_hil_readonly.py` or `python scripts/live_hil_readonly.py --port /dev/ttyUSB0 --cycles 30` — never writes (`read_only=True` + `execute_write` guard), writes `/tmp/live_hil_readonly_gate.json` `passed`.
2. **Gate 2 write guard** (`scripts/live_hil_write_gate.py:1`): `LIVE_HIL_ALLOW_WRITES=1 python scripts/live_hil_write_gate.py --check` verifies gate `<24h` → then ordered writes `DHW → modes → heating curve → hysteresis → schedule → clock` per `docs/live-hil.md:34`, re-reading after each.

## 5. Done criteria
- `pytest --cov` ≥95% on Python 3.14 — **met: 100% / 101 passed** (`docker compose run --rm test` `python 3.14.7`)
- hassfest + HACS clean — **met: `hassfest: success` `hacs: success`**
- Emulator clean — **met: `3 passed` in Docker + CI**
- Live parity / one low-risk write — **pending Phase 3 Gate 1**
