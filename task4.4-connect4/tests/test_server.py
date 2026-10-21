import asyncio
import random

import pytest

from connect4.scores import ScoreStore
from connect4.server import GameServer, LineReader, LineTooLong


def run(coro):
    return asyncio.run(coro)


async def start_server(**kwargs) -> GameServer:
    server = GameServer(host="127.0.0.1", port=0, rng_factory=lambda: random.Random(1), **kwargs)
    await server.start()
    return server


async def read_until(reader: asyncio.StreamReader, *markers: str, timeout: float = 5.0) -> str:
    """Read until one of the markers appears (or the server closes) and return all text read."""
    data = b""
    while not any(marker.encode() in data for marker in markers):
        chunk = await asyncio.wait_for(reader.read(4096), timeout)
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", errors="replace")


async def feed(data: bytes, max_line: int = 64, count: int = 1) -> list:
    stream = asyncio.StreamReader()
    stream.feed_data(data)
    stream.feed_eof()
    reader = LineReader(stream, max_line)
    results = []
    for _ in range(count):
        try:
            results.append(await reader.readline())
        except LineTooLong:
            results.append("<too long>")
    return results


def test_line_reader_accepts_every_line_ending():
    assert run(feed(b"a\r\nb\r\x00c\rd\ne", count=6)) == ["a", "b", "c", "d", None, None]


def test_line_reader_drops_telnet_negotiation():
    data = bytes([255, 253, 1]) + b"hi" + bytes([255, 250, 24, 1, 255, 240]) + b"\r\n"
    assert run(feed(data)) == ["hi"]


def test_line_reader_rejects_long_lines_and_recovers():
    assert run(feed(b"x" * 100 + b"\nok\n", count=2)) == ["<too long>", "ok"]


def test_line_reader_decodes_utf8():
    assert run(feed("Hoàng\n".encode("utf-8"))) == ["Hoàng"]


def test_banner_uses_crlf_and_asks_for_a_name():
    async def go():
        server = await start_server()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        text = await read_until(reader, "Your name")
        writer.close()
        await server.shutdown()
        return text

    text = run(go())
    assert text.startswith("CONNECT FOUR - SWE40006 Task 4.4 - host ")
    assert "\r\n" in text


def test_full_game_against_easy_cpu_is_recorded(tmp_path):
    scores = ScoreStore(tmp_path / "scores.db")

    async def go():
        server = await start_server(scores=scores)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        writer.write(b"Ana\r\n")
        await read_until(reader, "Choose a level")
        writer.write(b"1\r\n")
        text = await read_until(reader, "Your move")
        for _ in range(30):
            for col in "4321567":
                writer.write(f"{col}\r\n".encode())
                text = await read_until(reader, "Your move", "Play again?", "Choose another")
                if "Choose another" not in text:
                    break
            if "Play again?" in text:
                break
        writer.write(b"n\r\n")
        bye = await read_until(reader, "Bye")
        writer.close()
        await server.shutdown()
        return text, bye

    text, bye = run(go())
    assert "Play again?" in text
    assert "Thanks for playing, Ana. Bye!" in bye
    top = scores.top()
    assert top[0].name == "Ana" and top[0].wins + top[0].losses + top[0].draws == 1
    scores.close()


def test_two_sessions_are_independent():
    async def go():
        server = await start_server()
        r1, w1 = await asyncio.open_connection("127.0.0.1", server.bound_port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(r1, "Your name")
        await read_until(r2, "Your name")
        w1.write(b"Ana\r\n")
        w2.write(b"Bao\r\n")
        one, two = await read_until(r1, "level"), await read_until(r2, "level")
        w1.close()
        w2.close()
        await server.shutdown()
        return one, two

    one, two = run(go())
    assert "Hello, Ana!" in one and "Bao" not in one
    assert "Hello, Bao!" in two and "Ana" not in two


def test_extra_connections_get_server_busy():
    async def go():
        server = await start_server(max_sessions=1)
        r1, w1 = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(r1, "Your name")
        r2, w2 = await asyncio.open_connection("127.0.0.1", server.bound_port)
        busy = await read_until(r2, "busy")
        closed = await r2.read()
        w1.close()
        w2.close()
        await server.shutdown()
        return busy, closed

    busy, closed = run(go())
    assert busy == "Server busy, try again later.\r\n"
    assert closed == b""


def test_idle_players_are_disconnected():
    async def go():
        server = await start_server(idle_timeout=0.3)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        text = await read_until(reader, "inactivity")
        rest = await reader.read()
        writer.close()
        await server.shutdown()
        return text, rest

    text, rest = run(go())
    assert "Disconnected after inactivity." in text
    assert rest == b""


def test_long_input_is_refused_and_the_session_continues():
    async def go():
        server = await start_server()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        writer.write(b"y" * 100 + b"\r\n")
        refused = await read_until(reader, "too long")
        writer.write(b"Ana\r\n")
        hello = await read_until(reader, "level")
        writer.close()
        await server.shutdown()
        return refused, hello

    refused, hello = run(go())
    assert "Input too long (max 64 bytes)." in refused
    assert "Hello, Ana!" in hello


def test_quit_closes_the_connection():
    async def go():
        server = await start_server()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        writer.write(b"q\r\n")
        text = await read_until(reader, "Bye")
        rest = await reader.read()
        writer.close()
        await server.shutdown()
        return text, rest

    text, rest = run(go())
    assert "Thanks for playing. Bye!" in text
    assert rest == b""


def test_shutdown_warns_connected_players():
    async def go():
        server = await start_server()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        await server.shutdown(grace=2)
        text = await read_until(reader, "reconnect")
        rest = await reader.read()
        writer.close()
        return text, rest

    text, rest = run(go())
    assert "Server restarting" in text
    assert rest == b""


def test_a_failing_session_is_closed_and_the_server_keeps_running():
    from connect4.session import GameSession

    class Broken(GameSession):
        def handle(self, line):
            raise RuntimeError("bug")

    async def go():
        server = await start_server(session_factory=Broken)
        reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
        await read_until(reader, "Your name")
        writer.write(b"Ana\r\n")
        sorry = await read_until(reader, "reconnect")
        rest = await reader.read()
        server.session_factory = GameSession                  # the next player is served normally
        r2, w2 = await asyncio.open_connection("127.0.0.1", server.bound_port)
        banner = await read_until(r2, "Your name")
        writer.close()
        w2.close()
        await server.shutdown()
        return sorry, rest, banner

    sorry, rest, banner = run(go())
    assert "Sorry, something went wrong. Please reconnect." in sorry
    assert rest == b""
    assert banner.startswith("CONNECT FOUR")
