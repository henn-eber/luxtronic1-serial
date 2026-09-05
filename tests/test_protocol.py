"""Tests for the Luxtronik 1 protocol/encoding layer."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m pytest` from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components"))

from luxtronic1 import protocol  # noqa: E402
from luxtronic1.models import (  # noqa: E402
    BWSchedule,
    HeatingCurve,
    Overview,
    Temperatures,
    TempSettings,
)


def test_encode_command_bare() -> None:
    assert protocol.encode_command("1100") == b"1100\r\n"
    assert protocol.encode_command("999") == b"999\r\n"


def test_encode_command_with_values() -> None:
    assert protocol.encode_command("3406", [3]) == b"3406;1;3\r\n"
    assert protocol.encode_command("3501", [500]) == b"3501;1;500\r\n"


def test_decode_line_basic() -> None:
    line = protocol.decode_line(b"1100;12;10;20;30;40;50;60;500;70;80;90;100;110")
    assert line.command == "1100"
    assert line.count == 12
    assert line.values[:5] == [10, 20, 30, 40, 50]
    assert line.is_complete


def test_decode_line_handles_trailing_empty_fields() -> None:
    line = protocol.decode_line(b"3405;1;0;")
    assert line.command == "3405"
    assert line.count == 1
    assert line.values == [0]


def test_decode_line_rejects_non_ascii() -> None:
    import pytest

    with pytest.raises(protocol.FrameError):
        protocol.decode_line(b"\xff\xfe")


def test_has_complete_frame_true() -> None:
    buffer = b"1100;12;10;20;30;40;50;60;70;80;90;100;110;120\r\n"
    assert protocol.has_complete_frame(buffer, "1100") is True


def test_has_complete_frame_false_count_mismatch() -> None:
    buffer = b"1100;12;1;2;3\r\n"  # count says 12 but only 3 values
    assert protocol.has_complete_frame(buffer, "1100") is False


def test_line_terminator_993() -> None:
    assert protocol.line_terminator_993(b"993\r\n999\r\n") is True
    assert protocol.line_terminator_993(b"other\r\n") is False


def test_temperatures_from_values() -> None:
    t = Temperatures.from_values([1, 2, 3, 4, 5, 6, 500, 8, 9, 10, 11, 12])
    assert t.outdoor == 5
    assert t.dhw_setpoint == 500


def test_overview_from_lines_minimal() -> None:
    # The ioBroker adapter reads indices [2], [3], [4], [5], [6], [21]
    # from a 22-line block. Provide minimal lines to avoid crashes.
    lines = [""] * 22
    lines[2] = "1100;12;1;2;3;4;5;6;500;8;9;10;11;12"
    lines[3] = "1200;6;1;0;0;0;0;0"
    lines[4] = "1300;13;1;0;1;0;0;0;0;0;0;0;0;0;0"
    lines[5] = "1400;29;" + ";".join(["0"] * 29)
    lines[6] = "1600;9;0;0;0;0;0;0;0;0;0"
    lines[21] = "2900;4;LWPM;1.2;-2;0"
    overview = Overview.from_lines(lines)
    assert overview.temperatures.outdoor == 5
    assert overview.temperatures.dhw_setpoint == 500
    assert overview.inputs.evu is False
    assert overview.outputs.defrost_valve is True
    assert overview.outputs.underfloor_pump is True
    assert overview.status.wp_type == "LWPM"
    assert overview.status.software_version == "1.2"
    assert overview.status.anl_status_text == "Heating"


def test_heating_curve_roundtrip() -> None:
    curve = HeatingCurve.from_values([0, 0, 50, 30])
    assert curve.offset == 0
    assert curve.parallel_shift == 50
    assert curve.to_wire()[2] == 50
    assert len(curve.to_wire()) == 9  # padded with extras to 9 values


def test_bw_schedule_roundtrip() -> None:
    s = BWSchedule(start1_h=5, start1_m=30, end1_h=7, end1_m=0,
                   start2_h=18, start2_m=15, end2_h=22, end2_m=0)
    assert s.to_wire() == [5, 30, 7, 0, 18, 15, 22, 0]


def test_temp_settings_roundtrip() -> None:
    s = TempSettings(return_limit=1, hysteresis_heating=5,
                     hysteresis_dhw=5, flow_max=550)
    wire = s.to_wire()
    assert len(wire) == 16
    assert wire[1] == 5
    assert wire[7] == 5