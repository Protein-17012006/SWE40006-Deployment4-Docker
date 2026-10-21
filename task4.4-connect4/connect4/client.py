"""Minimal line client (a stand-in for `nc` on machines that lack it)."""

import asyncio
import codecs
import sys
import threading


async def run_client(host: str, port: int, stdin=None, stdout=None) -> int:
    """Relay stdin lines to the server and server text to stdout until the server closes."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as exc:
        stdout.write(f"Cannot connect to {host}:{port} - {exc}\n")
        stdout.flush()
        return 1

    loop = asyncio.get_running_loop()
    lines: asyncio.Queue = asyncio.Queue()

    def read_stdin() -> None:
        # A daemon thread, so a blocked readline() never keeps the process alive after the game ends.
        for line in stdin:
            loop.call_soon_threadsafe(lines.put_nowait, line)
        loop.call_soon_threadsafe(lines.put_nowait, None)

    threading.Thread(target=read_stdin, daemon=True).start()

    async def pump_input() -> None:
        while (line := await lines.get()) is not None:
            writer.write(line.rstrip("\r\n").encode("utf-8") + b"\r\n")
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()              # end of our input: let the server finish the session

    sender = asyncio.create_task(pump_input())
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        while data := await reader.read(4096):
            stdout.write(decoder.decode(data).replace("\r\n", "\n"))
            stdout.flush()
    except ConnectionError:
        pass
    finally:
        sender.cancel()
        writer.close()
    return 0
