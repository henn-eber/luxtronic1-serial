# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-19

### Added
- Initial public release for **AlphaInnotec / Siemens / Novelan Luxtronik 1** heat pumps via RS232 `57600 8N1` (`pyserial==3.5`, `pyserial-asyncio==0.6`).
- **Integration** (`custom_components/luxtronic1`): config flow with serial-port discovery (`serial.tools.list_ports`), reconfigure, options (`scan_interval` 30–3600s, `read_only` default `true`), `CONFIG_SCHEMA=config_entry_only`, `LuxtronikCoordinator` (`DataUpdateCoordinator`, `always_update=False`, `PARALLEL_UPDATES=1`), diagnostics with serial-path redaction.
- **Entities**: sensors (temperatures, operating hours, source/mix), binary sensors (EVU lockout, pressure, motor protection), `climate` (heating circuit `AUTO/HEAT/OFF` + `backup_heater/party/holiday` presets, `target_temperature` → `Abweichung Rücklauf Soll`), `water_heater` (DHW 30–65 °C `heat_pump/electric`).
- **Services** (`services.yaml`): `send_raw` (read-only guard `READ_COMMANDS`), `set_heating_curve`, `set_hysteresis`, `set_bw_schedule` (`HH:MM` `ServiceValidationError`), idempotent registration, `HomeAssistantError` on `779` desync (`0;0`+`999` abort).
- **Protocol** (`protocol.py`/`models.py` 22-line `1800` block): `1100`/`1800`/`2100`/`3200`/`3400`/`3405`/`3505` + write codes `3501/3406/3506/3401/2101/3201`, `WRITE_COOLDOWN 5.0`s, `779` desync recovery.
- **Testing**: `101 tests / 100%` `branch` (`pyproject.toml:27` `fail_under=95`, `1190` stmts) via `pytest-homeassistant-custom-component==0.13.364` `homeassistant==2026.9.1` `Python 3.14` (`python:3.14-slim` `docker-compose.yml:3`), `conftest.py:1` PHACC harness (`auto_enable_custom_integrations`), emulator HIL `tests/emulator/fake_luxtronik.py:155` `pty.openpty()` `FakeLuxtronik` (`CANNED` 1100/2100/…), live HIL two-gate `tests/test_live_hil_readonly.py` + `scripts/live_hil_readonly.py`/`live_hil_write_gate.py` (`docs/live-hil.md`).
- **CI** (`.github/workflows/ci.yaml:1` `checkout@v7`/`setup-python@v7` Node 24 `3.14`, `hassfest` `composite`, `hacs/action` `ignore: brands topics`, `pytest`/`emulator`, `dependabot.yml:1` grouped `ha-phacc`), `release.yaml:1` `tag v*.*.*` → `zip luxtronic1.zip` → `gh-release`.
- **HACS/HA quality**: `hacs.json:5` `homeassistant 2026.9.1`, `manifest.json:12` `version 0.1.0` `quality_scale: gold`, `brand/icon.png` `256×256` + `logo.png` `512×512` from `ait.jpg`, `strings.json`/`translations/de.json`/`icons.json`/`services.yaml`.

### Security
- Read-only mode default `true` (`const.py:40`); `client.py:69` `LuxtronikReadOnlyError` blocks all writes including `send_raw` non-`READ_COMMANDS`.

[0.1.0]: https://github.com/henn-eber/luxtronic1-serial/releases/tag/v0.1.0
