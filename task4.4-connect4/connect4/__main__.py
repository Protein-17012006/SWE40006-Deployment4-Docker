"""Command line: python -m connect4 [play|serve|client|leaderboard|healthcheck]."""

import argparse
import asyncio
import logging
import os
import random
import signal
import socket
import sqlite3
import sys
from pathlib import Path

from .client import run_client
from .render import render_standings
from .scores import ScoreStore
from .server import GameServer
from .session import GameSession


def open_scores(data_dir: str) -> ScoreStore | None:
    try:
        return ScoreStore(Path(data_dir) / "scores.db")
    except (OSError, sqlite3.Error) as exc:   # e.g. a read-only or missing data directory
        print(f"(scores are not saved: {exc})", file=sys.stderr)
        return None


def play(data_dir: str, color: bool) -> int:
    scores = open_scores(data_dir)
    session = GameSession(scores=scores, color=color)
    print(session.start(), end="", flush=True)
    while not session.finished:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        print(session.handle(line), end="", flush=True)
    return 0


async def serve(args) -> int:
    scores = open_scores(args.data)
    server = GameServer(args.host, args.port, scores, args.max_sessions, args.idle_timeout)
    await server.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError):  # Windows: Ctrl+C still stops asyncio.run
            pass
    await stop.wait()
    await server.shutdown()
    return 0


def leaderboard(data_dir: str) -> int:
    scores = open_scores(data_dir)
    if scores is None:
        return 1
    print(render_standings(scores.top(10)), end="")
    return 0


def healthcheck(host: str, port: int, timeout: float = 3.0) -> int:
    try:
        with socket.create_connection((host, port), timeout=timeout) as conn:
            conn.settimeout(timeout)
            banner = conn.recv(64)
    except OSError:
        return 1
    return 0 if banner.startswith(b"CONNECT FOUR") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="connect4", description="Connect Four against the CPU (SWE40006 Task 4.4).")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("play", help="play in this terminal (default)")
    p.add_argument("--data", default="/data", help="directory for scores.db")
    p.add_argument("--no-color", action="store_true", help="plain text board")

    s = sub.add_parser("serve", help="run the TCP game server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=2323)
    s.add_argument("--data", default="/data")
    s.add_argument("--max-sessions", type=int, default=32)
    s.add_argument("--idle-timeout", type=float, default=120.0)

    c = sub.add_parser("client", help="connect to a server (for machines without nc)")
    c.add_argument("host")
    c.add_argument("--port", type=int, default=2323)

    lb = sub.add_parser("leaderboard", help="print the top 10")
    lb.add_argument("--data", default="/data")

    hc = sub.add_parser("healthcheck", help="exit 0 if a local server answers")
    hc.add_argument("--host", default="127.0.0.1")
    hc.add_argument("--port", type=int, default=2323)
    # After add_subparsers, so that no sub-command means `play` with its defaults.
    parser.set_defaults(command="play", data="/data", no_color=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "play":
        return play(args.data, color=not args.no_color and "NO_COLOR" not in os.environ)
    if args.command == "serve":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        return asyncio.run(serve(args))
    if args.command == "client":
        return asyncio.run(run_client(args.host, args.port))
    if args.command == "leaderboard":
        return leaderboard(args.data)
    return healthcheck(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
