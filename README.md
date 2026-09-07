# Luxtronik 1 Heat Pump Controller Integration

A Home Assistant integration for **AlphaInnotec** (and compatible Siemens /
Novelan / etc.) heat pumps that use the **Luxtronik 1** controller without
the newer Ethernet port. Communication happens over the controller's
RS232 service port via a USB-to-RS232 adapter (57600 baud, 8N1).

> The protocol implementation is derived from the long-running
> [ioBroker.luxtronik1](https://github.com/iobroker-community-adapters/ioBroker.luxtronik1)
> adapter — same wire format, same handshake, same field names. If you have
> run that adapter against your heat pump, this integration speaks the
> exact same language.

## Features

* **Read-only sensors** for temperatures, runtimes, errors, software version
  and operating state.
* **Binary sensors** for compressor / pump / valve activity and fault
  inputs (EVU lockout, low/high pressure, motor protection).
* **Climate entity** for the heating circuit (mode + target return temperature).
* **Water heater entity** for the DHW (Brauchwasser) circuit (setpoint + mode).
* **Raw command service** (`luxtronic1.send_raw`) for diagnosing
  undocumented commands against your specific firmware.

## Hardware

The heat pump's service port is a DB-9 female with a classic null-modem
layout:

| DB-9 pin | Signal |
|----------|--------|
| 2        | RX (to PC) |
| 3        | TX (from PC) |
| 5        | GND |

Plug a USB-to-RS232 adapter (FTDI, CH340, Prolific etc.) into the port and
the other end into your Home Assistant host. The integration will list all
detected serial ports in the config flow.

> If you connect two DTE devices directly you may need a null-modem
> adapter (TX/RX swap).

## Installation

### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if you haven't already.
2. Add this repository as a **Custom repository** (Integration type).
3. Install **Luxtronik 1 Heat Pump**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & Services -> Add Integration** and pick
   **Luxtronik 1 Heat Pump**.

### Manual

Copy `custom_components/luxtronic1/` into your HA `config/custom_components/`
directory and restart Home Assistant.

## Configuration

During setup you are asked for:

| Field | Default | Notes |
|-------|---------|-------|
| Serial port | (auto-detected) | e.g. `/dev/ttyUSB0` on HA OS / Supervised, `COM3` on Windows |
| Baud rate | 57600 | Luxtronik 1 is hard-wired to 57600 |
| Parity | None | |
| Stop bits | 1 | |

The integration automatically opens the port once and reuses the same
serial connection until it fails, at which point it reconnects.

After setup you can change the **polling interval** (30–3600 seconds) from
the integration's options. Default is 300 s (5 min) — same as the
ioBroker adapter.

### Read-only mode (strict read/write separation)

Reading parameters and writing to the controller are strictly separated.
The integration options contain a **read-only mode** switch, which is
**enabled by default**:

* When enabled, *no* command that could change the controller is ever
  sent: all climate / water-heater controls disappear from the UI,
  the write services (`set_heating_curve`, `set_hysteresis`,
  `set_bw_schedule`) are rejected, and `send_raw` only accepts pure
  read commands (`1100`, `1800`, `2100`, `3200`, `3400`, `3405`,
  `3505`).
* To allow writes, disable read-only mode under **Settings → Devices &
  Services → Luxtronik 1 → Configure**. The entry reloads automatically.

Enforcement happens in the protocol client itself, so no entity or
service can bypass it. The transport detects controller `779` (desync)
responses and performs the standard abort (`0;0` + `999`) followed by a
reconnect.

## Entities

### Temperatures
* Outdoor temperature (°C)
* Flow temperature (°C)
* Return temperature (°C) + setpoint
* Hot-gas temperature (°C)
* DHW (Brauchwasser) temperature + setpoint
* Source-in / source-out (°C)
* Mixing-circuit 1 flow actual + setpoint (°C)

### Status
* Operating state (`Heating` / `Hot water` / `Swimming pool` /
  `Utility lockout` / `Defrost` / `Standby`)
* Compressor 1 / 2 running
* Heating pump running
* DHW circulation pump running
* Brine / source pump running
* Defrost valve open
* EVU lockout, high / low pressure, motor protection inputs (problem sensors)

### Counters
* Heat-pump total operating hours
* Compressor 1 / 2 lifetime hours & starts
* Current heat-pump run time (since last start)

### Climate (heating)
* HVAC modes: `Auto`, `Heat`, `Off`
* Preset modes: `Backup heater`, `Party`, `Holiday`
* Target = return setpoint (°C). Setting the target writes the heating
  curve's `Abweichung Rücklauf Soll` field.

### Water heater (DHW)
* Setpoint 30–65 °C
* Same modes as the heating side
* On/Off via mode switch

## Services

> All write services require read-only mode to be disabled (see above).
> `send_raw` always works for pure read commands.

### `luxtronic1.send_raw`
Send any ASCII command directly. Useful for diagnosing undocumented
commands.

```yaml
service: luxtronic1.send_raw
data:
  command: "1100"   # CRLF appended automatically
```

The response is logged at INFO level.

### `luxtronic1.set_heating_curve`
Patch one or more fields of the heating curve. Untouched fields keep their
current value.

```yaml
service: luxtronic1.set_heating_curve
data:
  heating_endpoint: 35   # Endpunkt
  night_setback: 2       # Nachtabsenkung
```

### `luxtronic1.set_hysteresis`
Patch the heating and/or DHW hysteresis.

### `luxtronic1.set_bw_schedule`
Set the two DHW time windows (HH:MM).

## Development

Run the unit tests locally:

```bash
python -m pytest tests/ -v
```

The tests only cover the protocol / data-model layer; they do **not** need
Home Assistant or pyserial-asyncio installed (the `conftest.py` stubs the
HA modules).

## Compatibility notes

* Tested conceptually against the protocol documented by the
  [ioBroker.luxtronik1](https://github.com/iobroker-community-adapters/ioBroker.luxtronik1)
  project. Field indices match `setfehlertext` / `setabschalttext` /
  `setstatustext` from that adapter.
* The integration assumes **no** other client is talking to the service
  port. If you have an existing ioBroker / Modbus gateway sharing the
  same RS232, only one will win.
* For older AlphaInnotec models with the Luxtronik 2 controller (the one
  with the Ethernet port) this integration will **not** work — that model
  uses a different protocol. Use one of the dedicated Luxtronik 2
  integrations instead.

## License

MIT. See [`LICENSE`](LICENSE).

## Credits

Protocol reference and wire format based on
[ioBroker.luxtronik1](https://github.com/iobroker-community-adapters/ioBroker.luxtronik1)
by forelleblau and iobroker-community-adapters.
