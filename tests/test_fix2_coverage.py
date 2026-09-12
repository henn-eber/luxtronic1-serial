"""Fix 2 — close remaining branch gaps (transport 94% etc.)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from luxtronic1.transport import LuxtronikTransport, SerialConfig
import luxtronic1.transport as tr_mod
from luxtronic1.client import LuxtronikClient
from luxtronic1.models import Overview, Temperatures, DigitalInputs, DigitalOutputs, Runtimes, OperatingHours, SystemStatus
from luxtronic1 import protocol


def _cfg():
    return SerialConfig(url="/dev/ttyUSB0")


def test_transport_read_until_complete_timeout_with_complete_true():
    """Hit transport.py 196->197 (TimeoutError with complete=True => break)."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        t._writer = MagicMock()
        t._writer.is_closing.return_value = False
        t._close_locked = AsyncMock()
        t._recover_from_desync_locked = AsyncMock()
        # reader will return a complete frame on first call, then TimeoutError
        calls = 0
        async def fake_read(n):
            nonlocal calls
            calls += 1
            if calls == 1:
                return b"1100;1;5\r\n"
            raise asyncio.TimeoutError()
        mr = MagicMock()
        mr.read = fake_read
        t._reader = mr

        # Patch wait_for: first call succeeds, second raises TimeoutError
        orig_wait = asyncio.wait_for
        call_idx = 0
        async def fake_wait(coro, timeout=None):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return await coro
            raise asyncio.TimeoutError()
        with patch("asyncio.wait_for", side_effect=fake_wait):
            res = await t._read_until_complete("1100", 1)
            assert len(res) == 1
            assert b"1100;1;5" in res[0]
    asyncio.run(_run())


def test_transport_read_until_complete_timeout_with_complete_false():
    """Hit transport.py 196->198 (TimeoutError with complete=False => continue)."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        t._writer = MagicMock()
        t._writer.is_closing.return_value = False
        t._close_locked = AsyncMock()
        t._recover_from_desync_locked = AsyncMock()
        seq = [b"1100;2;1\r\n", b"1100;1;5\r\n"]
        idx = 0
        async def fake_read(n):
            nonlocal idx
            if idx < len(seq):
                v = seq[idx]
                idx += 1
                return v
            return b""
        mr = MagicMock()
        mr.read = fake_read
        t._reader = mr
        call_idx = 0
        async def fake_wait(coro, timeout=None):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 2:
                raise asyncio.TimeoutError()
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            res = await t._read_until_complete("1100", 1)
            assert any(b"1100;1;5" in r for r in res)

    asyncio.run(_run())


def test_transport_read_until_complete_deadline_expiry():
    """Hit 192->233 branch — loop exits via deadline without complete."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        t._writer = MagicMock()
        t._writer.is_closing.return_value = False
        t._close_locked = AsyncMock()
        mr = MagicMock()
        async def fake_read(n):
            return b"1100;2;1\r\n"  # always incomplete
        mr.read = fake_read
        t._reader = mr
        # mock time: first call returns 0 (deadline = 8), second call >8 to exit loop
        mock_loop = MagicMock()
        mock_loop.time.side_effect = [0, 0, 9, 9]
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with patch("asyncio.wait_for", side_effect=fake_wait):
                with pytest.raises(Exception, match="Incomplete"):
                    await t._read_until_complete("1100", 2)
    asyncio.run(_run())


def test_transport_ensure_locked_writer_none():
    """Hit 161->167 branch — writer is None -> reconnect."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        t._connected = False
        t._writer = None
        t._reader = None
        t._close_locked = AsyncMock()
        mock_sa = MagicMock()
        async def fake_open(*a, **kw):
            mr = MagicMock()
            mw = MagicMock()
            mw.is_closing.return_value = False
            return (mr, mw)
        mock_sa.open_serial_connection = fake_open
        with patch.object(tr_mod, "serial_asyncio", mock_sa):
            await t._ensure_locked()
            assert t._connected is True
    asyncio.run(_run())


def test_transport_abort_success():
    """Hit 308-311 — full abort write/drain/sleep/write/drain."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        wr = MagicMock()
        wr.is_closing.return_value = False
        wr.write = MagicMock()
        wr.drain = AsyncMock()
        t._writer = wr
        await t._abort_locked(b"0;0\r\n")
        assert wr.write.call_count == 2
        assert wr.drain.call_count == 2
    asyncio.run(_run())


def test_transport_await_commit_timeout_with_terminator():
    """Hit 355->356 — TimeoutError but buffer has 993\\r\\n999 => return."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        mr = MagicMock()
        calls = 0
        async def fake_read(n):
            nonlocal calls
            calls += 1
            if calls == 1:
                return b"993\r\n999"
            raise asyncio.TimeoutError()
        mr.read = fake_read
        t._reader = mr
        # second wait_for will raise TimeoutError while buffer has terminator
        call_idx = 0
        async def fake_wait(coro, timeout=None):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return await coro
            raise asyncio.TimeoutError()
        with patch("asyncio.wait_for", side_effect=fake_wait):
            await t._await_commit(None)
    asyncio.run(_run())


def test_transport_await_commit_empty_chunk_break():
    """Hit 361->362 — empty chunk => break and return (non-fatal)."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        mr = MagicMock()
        async def fake_read(n):
            return b""
        mr.read = fake_read
        t._reader = mr
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            await t._await_commit(None)
    asyncio.run(_run())


def test_transport_await_commit_terminator_after_chunk():
    """Hit 364->349 — chunk contains terminator after read => return."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        mr = MagicMock()
        async def fake_read(n):
            return b"foo993\r\n999bar"
        mr.read = fake_read
        t._reader = mr
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            await t._await_commit(None)

def test_transport_close_locked_writer_none():
    """Hit 161->167 — _close_locked with writer None."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        t._writer = None
        t._reader = MagicMock()
        await t._close_locked()
        assert t._reader is None
        assert t._connected is False
        # also writer closing True path already covered via abort
    asyncio.run(_run())

def test_transport_await_commit_no_terminator_then_empty():
    """Hit 364->349 False branch — chunk without terminator, then empty break."""
    async def _run():
        t = LuxtronikTransport(MagicMock(), _cfg())
        mr = MagicMock()
        calls = 0
        async def fake_read(n):
            nonlocal calls
            calls += 1
            if calls == 1:
                return b"hello"
            return b""
        mr.read = fake_read
        t._reader = mr
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            await t._await_commit(None)
    asyncio.run(_run())


def test_client_decode_values_continue_branch():
    """Hit client.py 253->254 continue when command mismatch."""
    tr = MagicMock()
    tr.query = AsyncMock(return_value=[b"3405;1;1"])
    tr.execute_write = AsyncMock()
    c = LuxtronikClient(tr, read_only=False)
    # first line mismatched command, second matches
    vals = c._decode_values([b"1200;1;9", b"1100;2;10;20"], "1100", expected_count=2)
    assert vals == [10, 20]


def test_client_set_heating_curve_branches():
    """Hit client.py 179->181 etc — partial updates."""
    async def _run():
        tr = MagicMock()
        async def fake_query(cmd, expected_count=None):
            return [b"3400;9;1;2;3;4;5;6;7;8;9"]
        tr.query = fake_query
        tr.execute_write = AsyncMock()
        c = LuxtronikClient(tr, read_only=False)
        c._last_write = 0
        with patch("asyncio.sleep", new=AsyncMock()):
            # only offset
            await c.set_heating_curve(offset=1.0)
            # only endpoint
            await c.set_heating_curve(endpoint=2.0)
            # none (all None) — exercises 179->181 forward branch without mutation
            await c.set_heating_curve()
            assert tr.execute_write.call_count == 3
        # set_hysteresis branches 203->205 etc.
        async def fake_q2(cmd, expected_count=None):
            return [b"2100;16;" + b";".join([b"0"]*16)]
        tr.query = fake_q2
        with patch("asyncio.sleep", new=AsyncMock()):
            await c.set_hysteresis(heating=1.0)
            await c.set_hysteresis(dhw=2.0)
            await c.set_hysteresis()
    asyncio.run(_run())


def test_climate_preset_unknown_mode():
    """Hit climate.py 101->104 / 102->101 — unknown mode loop falls through."""
    from luxtronic1.climate import LuxtronikClimate
    coord = MagicMock()
    # mode 99 is not AUTO(0) nor OFF(4) nor in HEATING_PRESET_TO_MODE (1,2,3)
    coord.heating_mode = 99
    coord.hotwater_mode = 0
    coord.read_only = False
    coord.data = {"overview": MagicMock()}
    # overview needed for current_temperature etc but preset_mode only uses heating_mode
    coord.overview = MagicMock()
    coord.overview.temperatures = MagicMock(flow=100, return_setpoint=300)
    coord.overview.outputs = MagicMock(any_compressor_running=False)
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = "uid"
    entry.data = {"serial_port": "/dev/ttyUSB0"}
    clim = LuxtronikClimate(coord, entry)
    assert clim.preset_mode is None  # should hit final return None


def test_water_heater_supported_features_branch():
    """Hit water_heater.py 95->97 — read_only False returns features."""
    from luxtronic1 import water_heater as wh_mod
    from luxtronic1.water_heater import LuxtronikWaterHeater
    # stub in conftest lacks feature flags — patch if missing
    for attr, val in [("TARGET_TEMPERATURE", 1), ("OPERATION_MODE", 2), ("ON_OFF", 4)]:
        if not hasattr(wh_mod.WaterHeaterEntityFeature, attr):
            setattr(wh_mod.WaterHeaterEntityFeature, attr, wh_mod.WaterHeaterEntityFeature(val))
    coord = MagicMock()
    coord.hotwater_mode = 0
    coord.read_only = False
    coord.data = {"overview": MagicMock()}
    coord.overview = MagicMock()
    coord.overview.temperatures = MagicMock(dhw_actual=500, dhw_setpoint=600)
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = "uid"
    entry.data = {"serial_port": "/dev/ttyUSB0"}
    wh = LuxtronikWaterHeater(coord, entry)
    assert int(wh.supported_features) != 0
    coord.read_only = True
    assert int(wh.supported_features) == 0


def test_protocol_has_complete_frame_continue():
    """Hit protocol.py 127->128 continue when command mismatch."""
    # buffer contains a decodable line with different command, then correct one
    buf = b"1200;1;0\r\n1100;1;5\r\n"
    assert protocol.has_complete_frame(buf, "1100") is True
    # only mismatched command -> False
    assert protocol.has_complete_frame(b"1200;1;0\r\n", "1100") is False


def test_models_split_idx_overflow():
    """Hit models.py 324->325 — Overview.from_lines with short lines."""
    # split() should return [] when idx >= len(lines)
    # Provide minimal lines but call Overview.from_lines with only 3 lines -> idx 21 overflow
    # This should still parse status as default (empty) without crashing
    lines = ["1100;12;1;2;3;4;5;6;500;8;9;10;11;12",
             "1200;6;1;0;0;0;0;0",
             "1100;12;1;2;3;4;5;6;500;8;9;10;11;12"]  # only 3 lines
    # Need 6 lines minimum for temps to pass, but status at idx21 will be overflow
    # Instead provide exactly 7 lines where status missing
    lines = [""] * 7
    lines[2] = "1100;12;1;2;3;4;5;6;500;8;9;10;11;12"
    lines[3] = "1200;6;1;0;0;0;0;0"
    lines[4] = "1300;13;1;0;1;0;0;0;0;0;0;0;0;0;0"
    lines[5] = "1400;29;" + ";".join(["0"]*29)
    lines[6] = "1600;9;0;0;0;0;0;0;0;0;0"
    ov = Overview.from_lines(lines)
    assert ov.status.wp_type == ""  # default because idx21 overflow


def test_config_flow_async_get_options_flow():
    """Hit config_flow.py 151 — static async_get_options_flow."""
    from luxtronic1.config_flow import LuxtronikConfigFlow, LuxtronikOptionsFlow
    entry = MagicMock()
    flow = LuxtronikConfigFlow.async_get_options_flow(entry)
    assert isinstance(flow, LuxtronikOptionsFlow)
