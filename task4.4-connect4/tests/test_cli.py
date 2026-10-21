import asyncio
import random
import socket

from connect4.__main__ import build_parser, healthcheck, leaderboard, play
from connect4.server import GameServer


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_parser_defaults_to_play():
    args = build_parser().parse_args([])
    assert (args.command, args.data, args.no_color) == ("play", "/data", False)
    serve = build_parser().parse_args(["serve", "--port", "4000"])
    assert (serve.command, serve.port, serve.host) == ("serve", 4000, "0.0.0.0")


def test_healthcheck_exit_codes():
    async def go():
        server = GameServer(host="127.0.0.1", port=0, rng_factory=lambda: random.Random(1))
        await server.start()
        ok = await asyncio.to_thread(healthcheck, "127.0.0.1", server.bound_port)
        await server.shutdown()
        return ok

    assert asyncio.run(go()) == 0
    assert healthcheck("127.0.0.1", free_port(), timeout=1) == 1


def test_play_runs_a_dialogue_on_stdin(monkeypatch, capsys, tmp_path):
    answers = iter(["Ana", "q"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))
    assert play(str(tmp_path), color=False) == 0
    out = capsys.readouterr().out
    assert out.startswith("CONNECT FOUR")
    assert "Hello, Ana!" in out
    assert out.endswith("Thanks for playing, Ana. Bye!\n")


def test_leaderboard_on_an_empty_directory(capsys, tmp_path):
    assert leaderboard(str(tmp_path)) == 0
    assert capsys.readouterr().out == "No games recorded yet.\n"


def test_play_works_without_a_writable_data_directory(monkeypatch, capsys, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("a file where the data directory should be", encoding="utf-8")
    answers = iter(["Ana", "q"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))
    assert play(str(blocker), color=False) == 0
    captured = capsys.readouterr()
    assert "(scores are not saved:" in captured.err
    assert "Hello, Ana!" in captured.out
