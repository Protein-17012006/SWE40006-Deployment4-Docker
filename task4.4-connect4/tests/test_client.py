import asyncio
import io
import socket

from connect4.client import run_client


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_client_relays_both_ways():
    async def go():
        async def handler(reader, writer):
            writer.write(b"Hello\r\nYour name: ")
            await writer.drain()
            line = await reader.readline()
            writer.write(b"Got " + line.strip() + b"\r\nBye\r\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        out = io.StringIO()
        code = await run_client("127.0.0.1", port, stdin=io.StringIO("Hoàng\n"), stdout=out)
        server.close()
        await server.wait_closed()
        return code, out.getvalue()

    code, text = asyncio.run(go())
    assert code == 0
    assert text == "Hello\nYour name: Got Hoàng\nBye\n"


def test_client_reports_a_refused_connection():
    out = io.StringIO()
    code = asyncio.run(run_client("127.0.0.1", free_port(), stdin=io.StringIO(""), stdout=out))
    assert code == 1
    assert out.getvalue().startswith("Cannot connect to 127.0.0.1:")
