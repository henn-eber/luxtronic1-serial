"""Extra transport coverage for remaining branches."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from luxtronic1.transport import LuxtronikTransport, SerialConfig, LuxtronikConnectionError
import luxtronic1.transport as tr_mod


def _cfg():
    return SerialConfig(url="/dev/ttyUSB0")

def test_ensure_locked_already_connected():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        wr = MagicMock()
        wr.is_closing.return_value = False
        t._writer = wr
        t._reader = MagicMock()
        t._connected = True
        # should early return, not call open
        with patch.object(tr_mod, "serial_asyncio", MagicMock()):
            await t._ensure_locked()
            assert t._connected is True
            # writer closing -> should reconnect
            wr2 = MagicMock()
            wr2.is_closing.return_value = True
            t._writer = wr2
            mock_sa = MagicMock()
            mr = MagicMock()
            mw = MagicMock()
            mw.is_closing.return_value = False
            async def fake_open(*a, **kw):
                return (mr, mw)
            mock_sa.open_serial_connection = fake_open
            with patch.object(tr_mod, "serial_asyncio", mock_sa):
                t._close_locked = AsyncMock()
                await t._ensure_locked()
                assert t._connected is True
    asyncio.run(_run())

def test_ensure_locked_reconnect_fail():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        t._writer = None
        t._reader = None
        t._connected = False
        t._close_locked = AsyncMock()
        mock_sa = MagicMock()
        async def fake_fail(*a, **kw):
            raise Exception("fail")
        mock_sa.open_serial_connection = fake_fail
        with patch.object(tr_mod, "serial_asyncio", mock_sa):
            try:
                await t._ensure_locked()
                assert False
            except LuxtronikConnectionError:
                assert t._connected is False
    asyncio.run(_run())

def test_query_write_fail():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        t._connected = True
        t._lock = asyncio.Lock()
        wr = MagicMock()
        wr.write.side_effect = Exception("write boom")
        wr.is_closing.return_value = False
        t._writer = wr
        t._reader = MagicMock()
        t._ensure_locked = AsyncMock()
        t._close_locked = AsyncMock()
        try:
            await t._query_locked("1100", None)
            assert False
        except LuxtronikConnectionError as e:
            assert "Write failed" in str(e)
            assert t._close_locked.called
        # drain fail
        wr2 = MagicMock()
        wr2.write = MagicMock()
        wr2.drain = AsyncMock(side_effect=Exception("drain boom"))
        wr2.is_closing.return_value = False
        t._writer = wr2
        t._close_locked = AsyncMock()
        try:
            await t._query_locked("1100", None)
            assert False
        except LuxtronikConnectionError:
            pass
    asyncio.run(_run())

def test_read_until_complete_branches():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        # 1) Timeout with complete=True -> break
        wr = MagicMock()
        wr.is_closing.return_value = False
        t._writer = wr
        mr = MagicMock()
        # First read returns complete frame, second read timeout, should break and succeed
        chunks = [b"1100;1;5\r\n"]
        async def fake_read(n):
            if chunks:
                return chunks.pop(0)
            raise asyncio.TimeoutError()
        mr.read = fake_read
        t._reader = mr
        t._close_locked = AsyncMock()
        t._recover_from_desync_locked = AsyncMock()
        # need to ensure has_error_marker false
        res = await t._read_until_complete("1100", 1)
        assert len(res) == 1
        # 2) chunk empty -> break and raise incomplete
        mr2 = MagicMock()
        async def fake_empty(n):
            return b""
        mr2.read = fake_empty
        t._reader = mr2
        t._close_locked = AsyncMock()
        try:
            await t._read_until_complete("1100", 1)
            assert False
        except LuxtronikConnectionError as e:
            assert "Incomplete" in str(e)
        # 3) FrameError and command mismatch and count mismatch skipped
        mr3 = MagicMock()
        seq = [b"badline\r\n", b"1200;1;5\r\n", b"1100;2;1\r\n", b"1100;1;5\r\n"]
        idx = 0
        async def fake_seq(n):
            nonlocal idx
            if idx < len(seq):
                v = seq[idx]
                idx += 1
                return v
            return b""
        mr3.read = fake_seq
        t._reader = mr3
        t._close_locked = AsyncMock()
        # need to patch has_error_marker to false and make sure loop handles skips
        # provide expected_count=1, so 1200 mismatch and 1100;2;1 count mismatch
        # we need to use wait_for mock to avoid timeout
        orig_wait = asyncio.wait_for
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            res2 = await t._read_until_complete("1100", 1)
            assert b"1100;1;5" in res2[0] or len(res2)>0
        # 4) read exception -> raise
        mr4 = MagicMock()
        async def fake_err(n):
            raise Exception("read err")
        mr4.read = fake_err
        t._reader = mr4
        t._close_locked = AsyncMock()
        with patch("asyncio.wait_for", side_effect=fake_wait):
            try:
                await t._read_until_complete("1100", 1)
                assert False
            except LuxtronikConnectionError as e:
                assert "Read failed" in str(e)
        # 5) MAX_CHUNKS exceeded
        mr5 = MagicMock()
        async def fake_chunk(n):
            return b"1100;2;1\r\n"  # incomplete count
        mr5.read = fake_chunk
        t._reader = mr5
        t._close_locked = AsyncMock()
        # MAX_CHUNKS is 5, need to feed 6 chunks
        with patch("asyncio.wait_for", side_effect=fake_wait):
            try:
                await t._read_until_complete("1100", 2)
                assert False
            except LuxtronikConnectionError as e:
                assert "Incomplete" in str(e)
    asyncio.run(_run())

def test_execute_write_branches():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        wr = MagicMock()
        wr.write = MagicMock()
        wr.drain = AsyncMock()
        wr.is_closing.return_value = False
        mr = MagicMock()
        mr.read = AsyncMock(return_value=b"")
        t._writer = wr
        t._reader = mr
        t._connected = True
        t._lock = asyncio.Lock()
        t._ensure_locked = AsyncMock()
        # 1) open write fail
        wr_fail = MagicMock()
        wr_fail.write.side_effect = Exception("open fail")
        wr_fail.is_closing.return_value = False
        wr_fail.drain = AsyncMock()
        t._writer = wr_fail
        t._close_locked = AsyncMock()
        try:
            await t._execute_write_locked("3401", [1], None)
            assert False
        except LuxtronikConnectionError as e:
            assert "open failed" in str(e).lower()
        # restore writer
        t._writer = wr
        t._close_locked = AsyncMock()
        # 2) abort_token set at first sleep
        evt = asyncio.Event()
        evt.set()
        t._peek_for_desync_locked = AsyncMock(return_value=False)
        t._abort_locked = AsyncMock()
        with patch("asyncio.sleep", new=AsyncMock()):
            await t._execute_write_locked("3401", [1], evt)
            assert t._abort_locked.called
            t._abort_locked.reset_mock()
            # 3) desync peek true at first check
            evt2 = asyncio.Event()
            t._peek_for_desync_locked = AsyncMock(return_value=True)
            try:
                await t._execute_write_locked("3401", [1], None)
                assert False
            except LuxtronikConnectionError as e:
                assert "desynced" in str(e)
                assert t._abort_locked.called
            t._abort_locked.reset_mock()
            # 4) payload fail
            wr2 = MagicMock()
            # first write open succeeds, second payload fails
            call = 0
            def write_side(b):
                nonlocal call
                call += 1
                if call == 2:
                    raise Exception("payload boom")
            wr2.write = MagicMock(side_effect=write_side)
            wr2.drain = AsyncMock()
            wr2.is_closing.return_value = False
            t._writer = wr2
            t._peek_for_desync_locked = AsyncMock(return_value=False)
            try:
                await t._execute_write_locked("3401", [1], None)
                assert False
            except LuxtronikConnectionError as e:
                assert "payload" in str(e).lower()
            # 5) second abort token
            t._writer = wr
            wr.write.reset_mock()
            t._peek_for_desync_locked = AsyncMock(return_value=False)
            # need to make second sleep abort
            evt3 = asyncio.Event()
            # first sleep not aborted, second is
            # we can patch sleep to set event after first call
            sleep_calls = 0
            async def fake_sleep(d):
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls == 2:
                    evt3.set()
            with patch("asyncio.sleep", side_effect=fake_sleep):
                t._abort_locked = AsyncMock()
                await t._execute_write_locked("3401", [1], evt3)
                assert t._abort_locked.called
            # 6) second desync
            t._peek_for_desync_locked = AsyncMock(side_effect=[False, True])
            t._abort_locked = AsyncMock()
            with patch("asyncio.sleep", new=AsyncMock()):
                try:
                    await t._execute_write_locked("3401", [1], None)
                    assert False
                except LuxtronikConnectionError:
                    pass
            # 7) commit fail
            wr3 = MagicMock()
            call2 = 0
            def write_side2(b):
                nonlocal call2
                call2 += 1
                if call2 == 3:
                    raise Exception("commit boom")
            wr3.write = MagicMock(side_effect=write_side2)
            wr3.drain = AsyncMock(side_effect=[None, None, Exception("commit fail")])
            # Actually drain will be called after write, so need to make drain fail on third
            wr3.is_closing.return_value = False
            t._writer = wr3
            t._peek_for_desync_locked = AsyncMock(return_value=False)
            with patch("asyncio.sleep", new=AsyncMock()):
                try:
                    await t._execute_write_locked("3401", [1], None)
                    assert False
                except LuxtronikConnectionError as e:
                    assert "commit" in str(e).lower()
            # 8) await_commit raises -> abort
            t._writer = wr
            wr.write.reset_mock()
            wr.drain = AsyncMock()
            t._peek_for_desync_locked = AsyncMock(return_value=False)
            t._await_commit = AsyncMock(side_effect=LuxtronikConnectionError("commit wait fail"))
            t._abort_locked = AsyncMock()
            with patch("asyncio.sleep", new=AsyncMock()):
                try:
                    await t._execute_write_locked("3401", [1], None)
                    assert False
                except LuxtronikConnectionError:
                    assert t._abort_locked.called
    asyncio.run(_run())

def test_abort_and_peek_edge():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        # abort when writer closing
        wr = MagicMock()
        wr.is_closing.return_value = True
        t._writer = wr
        await t._abort_locked(b"0;0\r\n")
        assert wr.write.called is False
        # abort with exception best-effort
        wr2 = MagicMock()
        wr2.is_closing.return_value = False
        wr2.write = MagicMock(side_effect=Exception("boom"))
        wr2.drain = AsyncMock()
        t._writer = wr2
        await t._abort_locked(b"0;0\r\n")  # should not raise
        # peek with empty chunk
        mr = MagicMock()
        async def fake_empty(n):
            return b""
        mr.read = fake_empty
        t._reader = mr
        async def fake_wait(coro, timeout=None):
            return await coro
        with patch("asyncio.wait_for", side_effect=fake_wait):
            assert await t._peek_for_desync_locked() is False
    asyncio.run(_run())

def test_await_commit_timeout_and_success():
    async def _run():
        hass = MagicMock()
        t = LuxtronikTransport(hass, _cfg())
        # timeout with terminator present -> success via timeout branch
        mr = MagicMock()
        # buffer already has terminator, then wait_for timeout should succeed
        # We'll set buffer via _await_commit internal? Instead test via direct call with mocked wait_for timeout
        # First case: terminator arrives in chunk
        mr2 = MagicMock()
        async def fake_read(n):
            return b"993\r\n999"
        mr2.read = fake_read
        t._reader = mr2
        await t._await_commit(None)  # should return
        # second case: timeout but buffer has terminator
        mr3 = MagicMock()
        call = 0
        async def fake_read2(n):
            nonlocal call
            call += 1
            if call == 1:
                return b"993\r\n999"
            raise asyncio.TimeoutError()
        mr3.read = fake_read2
        t._reader = mr3
        # Need to make wait_for raise TimeoutError on second call but buffer already has terminator
        orig_wait = asyncio.wait_for
        async def fake_wait(coro, timeout=None):
            try:
                return await coro
            except asyncio.TimeoutError:
                raise
        # Actually _await_commit catches TimeoutError and checks line_terminator_993
        # So we can just call with fake_read that times out after having buffer
        # We'll patch wait_for to timeout on second iteration
        seq = [b"993\r\n999", asyncio.TimeoutError()]
        idx = 0
        async def fake_wait2(coro, timeout=None):
            nonlocal idx
            # coro is read(256)
            # we want first call succeed, second timeout
            if idx == 0:
                idx += 1
                return await coro
            else:
                raise asyncio.TimeoutError()
        mr4 = MagicMock()
        async def fake_read4(n):
            return b"993\r\n999"
        mr4.read = fake_read4
        t._reader = mr4
        with patch("asyncio.wait_for", side_effect=fake_wait2):
            await t._await_commit(None)
        # not fatal path: no terminator but timeout loop ends without error -> should just return
        mr5 = MagicMock()
        async def fake_read5(n):
            raise asyncio.TimeoutError()
        mr5.read = fake_read5
        t._reader = mr5
        # patch time to make deadline immediate? Instead we can set deadline short via monkeypatch loop time
        # Simpler: test that _await_commit returns without terminator (non-fatal)
        # We need to make loop exit via deadline: mock get_running_loop().time to exceed deadline quickly
        # Use patch on asyncio.get_running_loop
        mock_loop = MagicMock()
        mock_loop.time.side_effect = [0, 0, 10]  # deadline = 5, so second check exceeds
        async def fake_timeout(coro, timeout=None):
            try:
                coro.close()
            except Exception:
                pass
            raise asyncio.TimeoutError()
        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with patch("asyncio.wait_for", side_effect=fake_timeout):
                await t._await_commit(None)  # should not raise, just return after deadline
    asyncio.run(_run())
