"""Constants for the Luxtronik 1 protocol.

All numeric command codes are 4-digit (e.g. 1100, 3501) or 3-digit (999)
and correspond to the AlphaInnotec/Siemens Luxtronik 1 service interface.

Temperature values on the wire are integers in tenths of a degree Celsius
(°C x 10). The protocol layer keeps the raw integer; the HA entities
divide by 10.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "luxtronic1"
MANUFACTURER: Final = "AlphaInnotec"
DEFAULT_NAME: Final = "Luxtronik 1 Heat Pump"

# ----- Config keys -----------------------------------------------------------
CONF_SERIAL_PORT: Final = "serial_port"
CONF_BAUDRATE: Final = "baudrate"
CONF_PARITY: Final = "parity"
CONF_STOPBITS: Final = "stopbits"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_READ_ONLY: Final = "read_only"

# ----- Serial defaults -------------------------------------------------------
DEFAULT_BAUDRATE: Final = 57600
DEFAULT_BYTESIZE: Final = 8
DEFAULT_PARITY: Final = "N"
DEFAULT_STOPBITS: Final = 1

# ----- Polling ---------------------------------------------------------------
DEFAULT_SCAN_INTERVAL: Final = 300  # seconds; matches ioBroker default
WRITE_COOLDOWN: Final = 5.0  # seconds between consecutive writes

# ----- Access control --------------------------------------------------------
# Read-only mode blocks every write to the controller. It is the default
# because an unintended write can change the heating behavior of the house.
DEFAULT_READ_ONLY: Final = True

# Commands that only read controller state and are therefore allowed in
# read-only mode (including via the send_raw service).
READ_COMMANDS: Final = frozenset(
    {
        "1100",  # temperatures
        "1800",  # overview block
        "2100",  # temperature settings / hysteresis
        "3200",  # DHW weekly schedule
        "3400",  # heating curve
        "3405",  # heating mode
        "3505",  # hot water mode
        "2700",  # clock (read)
    }
)

# ----- Frame delimiters ------------------------------------------------------
CRLF: Final = b"\r\n"
TERMINATOR_OK: Final = b"993\r\n999"
ERROR_MARKER: Final = b"779"
COMMIT_CMD: Final = "999"
ABORT_CMD: Final = "0"

# ----- Read command codes ----------------------------------------------------
CMD_TEMPERATURES: Final = "1100"  # also delivered inside 1800 line [2]
CMD_OVERVIEW: Final = "1800"  # 22-line multi-block
CMD_TEMP_SETTINGS: Final = "2100"
CMD_BW_SCHEDULE: Final = "3200"
CMD_HEATING_CURVE: Final = "3400"
CMD_HEATING_MODE: Final = "3405"
CMD_HOTWATER_MODE: Final = "3505"
CMD_CLOCK_READ: Final = "2700"  # not used by ioBroker adapter; included for completeness

# ----- Write command codes ---------------------------------------------------
CMD_BW_SETPOINT_WRITE: Final = "3501"  # hot water setpoint
CMD_HEATING_MODE_WRITE: Final = "3406"
CMD_HOTWATER_MODE_WRITE: Final = "3506"
CMD_HEATING_CURVE_WRITE: Final = "3401"
CMD_HYSTERESIS_WRITE: Final = "2101"
CMD_BW_SCHEDULE_WRITE: Final = "3201"
CMD_CLOCK_WRITE: Final = "2701"

# ----- Mode values -----------------------------------------------------------
# From ioBroker adapter:
#   var modus = ['AUTO', 'ZWE', 'Party', 'Ferien', 'Aus', 'Aus'];
MODE_AUTO: Final = 0
MODE_ZWE: Final = 1  # Zweiter Waermeerzeuger (backup/boiler)
MODE_PARTY: Final = 2
MODE_HOLIDAY: Final = 3
MODE_OFF: Final = 4
MODE_OFF_ALT: Final = 5

HEATING_MODES: Final = {
    MODE_AUTO: "Automatic",
    MODE_ZWE: "Backup heater",
    MODE_PARTY: "Party",
    MODE_HOLIDAY: "Holiday",
    MODE_OFF: "Off",
    MODE_OFF_ALT: "Off",
}

HOTWATER_MODES: Final = {
    MODE_AUTO: "Automatic",
    MODE_ZWE: "Backup heater",
    MODE_PARTY: "Party",
    MODE_HOLIDAY: "Holiday",
    MODE_OFF: "Off",
    MODE_OFF_ALT: "Off",
}

# ----- Operating status (ANL status) -----------------------------------------
ANL_STATUS_HEATING: Final = 0
ANL_STATUS_HOTWATER: Final = 1
ANL_STATUS_POOL: Final = 2
ANL_STATUS_EVU_LOCK: Final = 3
ANL_STATUS_DEFROST: Final = 4
ANL_STATUS_STANDBY: Final = 5

ANL_STATUS_TEXT: Final = {
    ANL_STATUS_HEATING: "Heating",
    ANL_STATUS_HOTWATER: "Hot water",
    ANL_STATUS_POOL: "Swimming pool",
    ANL_STATUS_EVU_LOCK: "Utility lockout",
    ANL_STATUS_DEFROST: "Defrost",
    ANL_STATUS_STANDBY: "Standby",
}

# ----- Error / shutdown text tables ------------------------------------------
# From ioBroker setfehlertext / setabschalttext (lines 1751-1866).
# These are decoded from the wire codes returned in the 1800 block.

FEHLER_CODES: Final = {
    11: "No error",
    701: "Low-pressure fault",
    702: "Low-pressure lockout",
    703: "Frost protection",
    704: "Hot-gas fault",
    705: "Motor protection VEN",
    706: "",
    707: "Heat pump coding",
    708: "Return sensor",
    709: "Flow sensor",
    710: "Hot-gas sensor",
    711: "Outdoor sensor",
    712: "DHW sensor",
    713: "Source-in sensor",
    714: "Hot-gas DHW",
    715: "High-pressure cut-off",
    716: "High-pressure fault",
    717: "Source flow",
    718: "Max. outdoor temp.",
    719: "Min. outdoor temp.",
    720: "Source temperature",
    721: "Low-pressure cut-off",
    722: "Temp diff. heating water",
    723: "Temp diff. DHW",
    724: "Temp diff. defrost",
    725: "System error DHW",
    726: "Mixing circuit 1 sensor",
    727: "Brine pressure",
    728: "Source-out sensor",
    729: "Phase rotation",
    730: "Heat-up power",
    731: "",
    732: "Cooling fault",
    733: "Anode fault",
    734: "Anode fault",
    735: "Ext. energy sensor",
    736: "Solar collector sensor",
    737: "Solar tank sensor",
    738: "Mixing circuit 2 sensor",
    739: "CAN error: WP missing",
    740: "CAN error: timeout",
    741: "CAN error: bus off",
    742: "CAN error: data",
    743: "CAN error: address",
    744: "",
    745: "Modem error",
}

ABSCHALT_CODES: Final = {
    10: "Less heat",
    1: "Heat pump fault",
    2: "System fault",
}