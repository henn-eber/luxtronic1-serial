"""Typed data model for Luxtronik 1.

Each ``CMD*`` read response is parsed into a small dataclass so the rest of
the integration never has to remember which integer index means what.

The scale for temperature-like fields is **tenths of a degree Celsius** on
the wire; the dataclasses keep the raw integer (so a roundtrip is exact)
and expose a ``*_celsius`` property for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .const import (
    ABSCHALT_CODES,
    ANL_STATUS_TEXT,
    FEHLER_CODES,
)


def _signed(value: int) -> int:
    """Reserved for future use: some Luxtronik fields wrap a 16-bit range.

    Current firmware returns plain signed integers; this helper exists so
    that if/when we encounter a wrapped field we have a single conversion
    site.
    """

    return value - 0x10000 if value > 0x7FFF else value


# ---------------------------------------------------------------------------
# Read blocks
# ---------------------------------------------------------------------------


@dataclass
class Temperatures:
    """1100 — live temperature snapshot (also embedded in 1800 line [2])."""

    flow: int = 0  # Vorlauf
    return_: int = 0  # Rücklauf
    return_setpoint: int = 0  # Rücklauf-Soll
    hot_gas: int = 0  # Heissgas
    outdoor: int = 0  # Aussentemperatur
    dhw_actual: int = 0  # Brauchwasser Ist
    dhw_setpoint: int = 0  # Brauchwasser Soll
    source_in: int = 0  # Wärmequelle Ein
    source_out: int = 0  # Wärmequelle Aus
    mix1_flow_actual: int = 0  # MK1 Vorlauf Ist
    mix1_flow_setpoint: int = 0  # MK1 Vorlauf Soll
    return_secondary: int = 0  # RS

    @classmethod
    def from_values(cls, values: list[int]) -> "Temperatures":
        """Parse from a 12-value payload (``1100``)."""

        if len(values) < 12:
            raise ValueError(f"1100: expected 12 values, got {len(values)}")
        return cls(
            flow=values[0],
            return_=values[1],
            return_setpoint=values[2],
            hot_gas=values[3],
            outdoor=values[4],
            dhw_actual=values[5],
            dhw_setpoint=values[6],
            source_in=values[7],
            source_out=values[8],
            mix1_flow_actual=values[9],
            mix1_flow_setpoint=values[10],
            return_secondary=values[11],
        )

    @property
    def outdoor_celsius(self) -> float:
        return self.outdoor / 10.0


@dataclass
class DigitalInputs:
    """1200 — binary inputs (inside 1800 line [3])."""

    asd: bool = False
    evu: bool = False
    hd: bool = False
    mot: bool = False
    nd: bool = False
    pex: bool = False

    @classmethod
    def from_values(cls, values: list[int]) -> "DigitalInputs":
        if len(values) < 6:
            raise ValueError(f"1200: expected 6 values, got {len(values)}")
        return cls(
            asd=bool(values[0]),
            evu=bool(values[1]),
            hd=bool(values[2]),
            mot=bool(values[3]),
            nd=bool(values[4]),
            pex=bool(values[5]),
        )


@dataclass
class DigitalOutputs:
    """1300 — binary outputs (inside 1800 line [4])."""

    defrost_valve: bool = False
    dhw_circulation_pump: bool = False
    underfloor_pump: bool = False
    heating_pump: bool = False
    mix1_open: bool = False
    mix1_close: bool = False
    housing_fan: bool = False
    brine_pump_or_source_fan: bool = False
    compressor_1: bool = False
    compressor_2: bool = False
    extra_circulation_pump: bool = False
    backup_generator_1: bool = False
    backup_generator_2_fault: bool = False

    @classmethod
    def from_values(cls, values: list[int]) -> "DigitalOutputs":
        if len(values) < 13:
            raise ValueError(f"1300: expected 13 values, got {len(values)}")
        return cls(
            defrost_valve=bool(values[0]),
            dhw_circulation_pump=bool(values[1]),
            underfloor_pump=bool(values[2]),
            heating_pump=bool(values[3]),
            mix1_open=bool(values[4]),
            mix1_close=bool(values[5]),
            housing_fan=bool(values[6]),
            brine_pump_or_source_fan=bool(values[7]),
            compressor_1=bool(values[8]),
            compressor_2=bool(values[9]),
            extra_circulation_pump=bool(values[10]),
            backup_generator_1=bool(values[11]),
            backup_generator_2_fault=bool(values[12]),
        )

    @property
    def any_compressor_running(self) -> bool:
        return self.compressor_1 or self.compressor_2


@dataclass
class Runtimes:
    """1400 — current runtimes since last start."""

    wp_seconds: int = 0
    zwe1_seconds: int = 0
    zwe2_seconds: int = 0
    netzeinv: int = 0
    ssp_stand_seconds: int = 0
    ssp_verz_seconds: int = 0
    vd_stand_seconds: int = 0
    hrm_seconds: int = 0
    hrw_seconds: int = 0
    tdi_seconds: int = 0
    bw_lock_seconds: int = 0

    @classmethod
    def from_values(cls, values: list[int]) -> "Runtimes":
        # Wire layout: hh,mm,ss for each duration except Netzeinv (single).
        if len(values) < 29:
            raise ValueError(f"1400: expected 29 values, got {len(values)}")

        def hms(off: int) -> int:
            return values[off] * 3600 + values[off + 1] * 60 + values[off + 2]

        def ms(off: int) -> int:
            return values[off] * 60 + values[off + 1]

        return cls(
            wp_seconds=hms(0),
            zwe1_seconds=hms(3),
            zwe2_seconds=hms(6),
            netzeinv=values[9],
            ssp_stand_seconds=ms(10),
            ssp_verz_seconds=ms(12),
            vd_stand_seconds=hms(14),
            hrm_seconds=hms(17),
            hrw_seconds=hms(20),
            tdi_seconds=hms(23),
            bw_lock_seconds=hms(26),
        )


@dataclass
class OperatingHours:
    """``betriebsstunden`` from 1800 line [6]."""

    compressor_1: int = 0
    compressor_1_starts: int = 0
    compressor_1_avg: int = 0
    compressor_2: int = 0
    compressor_2_starts: int = 0
    compressor_2_avg: int = 0
    zwe1: int = 0
    zwe2: int = 0
    heat_pump_total: int = 0

    @classmethod
    def from_values(cls, values: list[int]) -> "OperatingHours":
        if len(values) < 9:
            raise ValueError(f"hours block: expected 9 values, got {len(values)}")
        return cls(
            compressor_1=values[0],
            compressor_1_starts=values[1],
            compressor_1_avg=values[2],
            compressor_2=values[3],
            compressor_2_starts=values[4],
            compressor_2_avg=values[5],
            zwe1=values[6],
            zwe2=values[7],
            heat_pump_total=values[8],
        )


@dataclass
class FaultRecord:
    """One entry from the 5-row error / shutdown log."""

    code: int
    text: str
    timestamp: str  # formatted DD.MM.YY hh:mm

    @classmethod
    def from_line(cls, line: str, table: dict[int, str]) -> Optional["FaultRecord"]:
        """Parse a single ``;<code>;<day>;<month>;<year2>;<hh>;<mm>;<ss>`` line.

        Returns ``None`` for "no error" entries (code 11) so the caller can
        skip them.
        """

        parts = line.split(";")
        if len(parts) < 8:
            return None
        try:
            code = int(parts[1])
            day = int(parts[2])
            month = int(parts[3])
            year = int(parts[4])
            hh = int(parts[5])
            mm = int(parts[6])
        except ValueError:
            return None
        if code == 11:  # "kein Fehler"
            return None
        text = table.get(code, "")
        timestamp = f"{day:02d}.{month:02d}.{year:02d} {hh:02d}:{mm:02d}"
        return cls(code=code, text=text, timestamp=timestamp)


@dataclass
class SystemStatus:
    """2900 / 1800 line [21]."""

    wp_type: str = ""
    software_version: str = ""
    bivalent_stage: str = ""
    anl_status: int = 0
    anl_status_text: str = "Unknown"

    @classmethod
    def from_values(cls, values: list[str]) -> "SystemStatus":
        """``values`` are the fields *after* the command and count.

        Wire layout: [wp_type, software, bivalent, anl_status_code]
        The first three are decimal strings of letters/digits; the last is
        the ANL operating state (integer).
        """

        if len(values) < 4:
            raise ValueError(f"status block: expected >=4 values, got {len(values)}")
        anl_status = int(values[3])
        return cls(
            wp_type=values[0],
            software_version=values[1],
            bivalent_stage=values[2],
            anl_status=anl_status,
            anl_status_text=ANL_STATUS_TEXT.get(anl_status, "Unknown"),
        )


@dataclass
class Overview:
    """Full ``1800`` multi-line snapshot."""

    temperatures: Temperatures = field(default_factory=Temperatures)
    inputs: DigitalInputs = field(default_factory=DigitalInputs)
    outputs: DigitalOutputs = field(default_factory=DigitalOutputs)
    runtimes: Runtimes = field(default_factory=Runtimes)
    hours: OperatingHours = field(default_factory=OperatingHours)
    errors: list[FaultRecord] = field(default_factory=list)
    shutdowns: list[FaultRecord] = field(default_factory=list)
    status: SystemStatus = field(default_factory=SystemStatus)

    @classmethod
    def from_lines(cls, lines: list[str]) -> "Overview":
        """Parse the 22 CRLF-delimited lines returned by ``1800``.

        Mirrors ioBroker lines:
            [2]  -> 1100 temps
            [3]  -> 1200 inputs
            [4]  -> 1300 outputs
            [5]  -> 1400 runtimes
            [6]  -> hours
            [8..12] -> 5 errors
            [15..19] -> 5 shutdowns
            [21] -> 2900 status
        """

        def split(idx: int) -> list[int]:
            if idx >= len(lines):
                return []
            return [int(x) for x in lines[idx].split(";")[2:] if x]

        def split_str(idx: int) -> list[str]:
            if idx >= len(lines):
                return []
            return [x for x in lines[idx].split(";")[2:] if x]

        temps = Temperatures.from_values(split(2))
        inputs = DigitalInputs.from_values(split(3))
        outputs = DigitalOutputs.from_values(split(4))
        runtimes = Runtimes.from_values(split(5))
        hours = OperatingHours.from_values(split(6))

        errors = [
            FaultRecord.from_line(lines[i], FEHLER_CODES)
            for i in range(8, 13)
            if i < len(lines)
        ]
        errors = [e for e in errors if e is not None]

        shutdowns = [
            FaultRecord.from_line(lines[i], ABSCHALT_CODES)
            for i in range(15, 20)
            if i < len(lines)
        ]
        shutdowns = [s for s in shutdowns if s is not None]

        status_values = split_str(21)
        status = SystemStatus.from_values(status_values) if status_values else SystemStatus()

        return cls(
            temperatures=temps,
            inputs=inputs,
            outputs=outputs,
            runtimes=runtimes,
            hours=hours,
            errors=errors,
            shutdowns=shutdowns,
            status=status,
        )


@dataclass
class TempSettings:
    """2100 — temperature limits and hysteresis."""

    return_limit: int = 0
    hysteresis_heating: int = 0
    max_dhw_boost: int = 0
    release_2nd_compressor: int = 0
    release_backup: int = 0
    air_defrost_temp: int = 0
    tdi_setpoint: int = 0
    hysteresis_dhw: int = 0
    vl2_vd_bw: int = 0
    outdoor_max: int = 0
    outdoor_min: int = 0
    source_temp_min: int = 0
    hot_gas_max: int = 0
    air_defrost_end_temp: int = 0
    setback_lower_limit: int = 0
    flow_max: int = 0

    @classmethod
    def from_values(cls, values: list[int]) -> "TempSettings":
        if len(values) < 16:
            raise ValueError(f"2100: expected 16 values, got {len(values)}")
        return cls(
            return_limit=values[0],
            hysteresis_heating=values[1],
            max_dhw_boost=values[2],
            release_2nd_compressor=values[3],
            release_backup=values[4],
            air_defrost_temp=values[5],
            tdi_setpoint=values[6],
            hysteresis_dhw=values[7],
            vl2_vd_bw=values[8],
            outdoor_max=values[9],
            outdoor_min=values[10],
            source_temp_min=values[11],
            hot_gas_max=values[12],
            air_defrost_end_temp=values[13],
            setback_lower_limit=values[14],
            flow_max=values[15],
        )

    def to_wire(self) -> list[int]:
        return [
            self.return_limit,
            self.hysteresis_heating,
            self.max_dhw_boost,
            self.release_2nd_compressor,
            self.release_backup,
            self.air_defrost_temp,
            self.tdi_setpoint,
            self.hysteresis_dhw,
            self.vl2_vd_bw,
            self.outdoor_max,
            self.outdoor_min,
            self.source_temp_min,
            self.hot_gas_max,
            self.air_defrost_end_temp,
            self.setback_lower_limit,
            self.flow_max,
        ]


@dataclass
class HeatingCurve:
    """3400 / 3401 — heating curve parameters."""

    offset: int = 0  # Abweichung Rücklauf Soll
    endpoint: int = 0  # Endpunkt
    parallel_shift: int = 0  # Parallelverschiebung
    night_setback: int = 0  # Nachtabsenkung
    extras: list[int] = field(default_factory=list)  # indices [6..10], echoed unchanged

    @classmethod
    def from_values(cls, values: list[int]) -> "HeatingCurve":
        if len(values) < 4:
            raise ValueError(f"3400: expected >=4 values, got {len(values)}")
        return cls(
            offset=values[0],
            endpoint=values[1],
            parallel_shift=values[2],
            night_setback=values[3],
            extras=list(values[4:]),
        )

    def to_wire(self) -> list[int]:
        out = [
            self.offset,
            self.endpoint,
            self.parallel_shift,
            self.night_setback,
        ]
        # Pad with up to 5 trailing fields (heat-pump expects count=9, so 9 values total).
        extras = list(self.extras)
        while len(extras) < 5:
            extras.append(0)
        out.extend(extras)
        return out[:9]


@dataclass
class BWSchedule:
    """3200 / 3201 — DHW weekly time window."""

    start1_h: int = 0
    start1_m: int = 0
    end1_h: int = 0
    end1_m: int = 0
    start2_h: int = 0
    start2_m: int = 0
    end2_h: int = 0
    end2_m: int = 0

    @classmethod
    def from_values(cls, values: list[int]) -> "BWSchedule":
        if len(values) < 8:
            raise ValueError(f"3200: expected 8 values, got {len(values)}")
        return cls(
            start1_h=values[0],
            start1_m=values[1],
            end1_h=values[2],
            end1_m=values[3],
            start2_h=values[4],
            start2_m=values[5],
            end2_h=values[6],
            end2_m=values[7],
        )

    def to_wire(self) -> list[int]:
        return [
            self.start1_h,
            self.start1_m,
            self.end1_h,
            self.end1_m,
            self.start2_h,
            self.start2_m,
            self.end2_h,
            self.end2_m,
        ]


@dataclass
class Clock:
    """2701 write payload (no 2700 read exists in ioBroker adapter)."""

    day: int = 0
    month: int = 0
    year: int = 0  # two-digit
    dow: int = 0  # 0=Mon ... 6=Sun
    hour: int = 0
    minute: int = 0
    second: int = 0

    def to_wire(self) -> list[int]:
        return [
            self.day,
            self.month,
            self.year,
            self.dow,
            self.hour,
            self.minute,
            self.second,
        ]