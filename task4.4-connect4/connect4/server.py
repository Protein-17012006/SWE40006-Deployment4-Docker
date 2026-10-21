"""asyncio TCP server: one independent GameSession per connection, safe to expose to the internet."""

import asyncio
import logging
import random
import socket

from .session import GameSession

log = logging.getLogger("connect4.server")

IAC, SB, SE = 255, 250, 240
WILL, WONT, DO, DONT = 251, 252, 253, 254
CR, LF, NUL = 13, 10, 0


class LineTooLong(Exception):
    """The client sent more than max_line bytes before a line break."""


class LineReader:
    """Reads lines from a raw TCP stream.

    Telnet IAC sequences are dropped, and CR LF, CR NUL, CR and LF all end a line.
    """

    def __init__(self, reader: asyncio.StreamReader, max_line: int) -> None:
        self._reader = reader
        self._max = max_line
        self._after_cr = False

    async def _byte(self) -> int | None:
        data = await self._reader.read(1)
        return data[0] if data else None

    async def _skip_telnet_command(self) -> None:
        command = await self._byte()
        if command in (WILL, WONT, DO, DONT):
            await self._byte()                     # the option byte
        elif command == SB:                        # sub-negotiation runs until IAC SE
            previous = None
            while True:
                byte = await self._byte()
                if byte is None or (previous == IAC and byte == SE):
                    return
                previous = byte

    async def readline(self) -> str | None:
        """Return the next line without its line break, or None at end of stream."""
        buffer = bytearray()
        too_long = False
        while True:
            byte = await self._byte()
            if byte is None:
                return None
            if byte == IAC:
                await self._skip_telnet_command()
                continue
            if self._after_cr:
                self._after_cr = False
                if byte in (LF, NUL):              # second half of CR LF or CR NUL
                    continue
            if byte == CR:
                self._after_cr = True
                break
            if byte == LF:
                break
            if len(buffer) >= self._max:
                too_long = True
                continue
            buffer.append(byte)
        if too_long:
            raise LineTooLong
        return buffer.decode("utf-8", errors="replace")


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 2323, scores=None, max_sessions: int = 32,
                 idle_timeout: float = 120.0, max_line: int = 64, rng_factory=random.Random,
                 session_factory=GameSession) -> None:
        self.host = host
        self.port = port
        self.scores = scores
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.max_line = max_line
        self.rng_factory = rng_factory
        self.session_factory = session_factory
        self.hostname = socket.gethostname()
        self._server = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def bound_port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("listening on %s:%s", self.host, self.bound_port)

    async def shutdown(self, grace: float = 5.0) -> None:
        """Stop accepting, tell connected players, and close within `grace` seconds."""
        if self._server is not None:
            self._server.close()
        for writer in list(self._writers):
            try:
                writer.write(b"\r\nServer restarting - please reconnect in a minute.\r\n")
            except (ConnectionError, RuntimeError):
                pass
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=grace)
        log.info("server stopped")

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, text: str) -> None:
        writer.write(text.replace("\n", "\r\n").encode("utf-8"))
        await writer.drain()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername") or ("?", 0)
        if len(self._tasks) >= self.max_sessions:
            try:
                await self._send(writer, "Server busy, try again later.\n")
            finally:
                writer.close()
            log.warning("refused %s:%s (server busy)", peer[0], peer[1])
            return
        task = asyncio.current_task()
        self._tasks.add(task)
        self._writers.add(writer)
        session = self.session_factory(
            scores=self.scores, rng=self.rng_factory(), host=self.hostname,
            on_result=lambda *r: log.info("game over name=%r level=%s outcome=%s moves=%s", *r))
        lines = LineReader(reader, self.max_line)
        reason = "client left"
        try:
            await self._send(writer, session.start())
            while not session.finished:
                try:
                    line = await asyncio.wait_for(lines.readline(), self.idle_timeout)
                except asyncio.TimeoutError:
                    await self._send(writer, "\nDisconnected after inactivity.\n")
                    reason = "idle timeout"
                    break
                except LineTooLong:
                    await self._send(writer, f"Input too long (max {self.max_line} bytes).\n")
                    continue
                if line is None:
                    break
                await self._send(writer, await asyncio.to_thread(session.handle, line))
            else:
                reason = "player quit"
        except asyncio.CancelledError:
            reason = "server shutdown"
            raise
        except ConnectionError:
            reason = "connection lost"
        except Exception:                       # a bug must end one session, never the server
            log.exception("session %s:%s failed", peer[0], peer[1])
            reason = "server error"
            try:
                await self._send(writer, "\nSorry, something went wrong. Please reconnect.\n")
            except ConnectionError:
                pass
        finally:
            self._tasks.discard(task)
            self._writers.discard(writer)
            writer.close()
            # Health checks connect from inside the container and leave before giving a name.
            if session.name or peer[0] not in ("127.0.0.1", "::1"):
                log.info("session %s:%s name=%r ended: %s", peer[0], peer[1], session.name, reason)
