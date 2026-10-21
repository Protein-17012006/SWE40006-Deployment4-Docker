import importlib
import socket

import pytest
from redis import RedisError

import app as hello


class CountingRedis:
    def __init__(self):
        self.count = 0

    def incr(self, key):
        assert key == "counter"
        self.count += 1
        return self.count


class DownRedis:
    def incr(self, key):
        raise RedisError("Error 111 connecting to redis:6379. Connection refused.")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NAME", "SWE40006")
    monkeypatch.setenv("DEPLOY_TARGET", "Laptop · pytest")
    monkeypatch.setattr(hello, "redis", CountingRedis())
    return hello.app.test_client()


def page(client) -> str:
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_greets_name_and_shows_the_container_hostname(client):
    body = page(client)
    assert "<h3>Hello SWE40006!</h3>" in body
    assert f"<b>Hostname:</b> {socket.gethostname()}" in body


def test_name_defaults_to_world(client, monkeypatch):
    monkeypatch.delenv("NAME")
    assert "<h3>Hello World!</h3>" in page(client)


def test_visits_go_up_on_every_request(client):
    assert "<b>Visits:</b> 1" in page(client)
    assert "<b>Visits:</b> 2" in page(client)


def test_page_still_works_when_redis_is_down(client, monkeypatch):
    monkeypatch.setattr(hello, "redis", DownRedis())
    assert "<i>cannot connect to Redis, counter disabled</i>" in page(client)


def test_counter_is_disabled_without_redis_host(client, monkeypatch):
    monkeypatch.setattr(hello, "redis", None)
    assert "<i>cannot connect to Redis, counter disabled</i>" in page(client)


def test_name_is_html_escaped(client, monkeypatch):
    monkeypatch.setenv("NAME", "<script>alert(1)</script>")
    body = page(client)
    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_healthz_does_not_need_redis(client, monkeypatch):
    monkeypatch.setattr(hello, "redis", DownRedis())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"


def test_footer_shows_where_it_runs(client):
    body = page(client)
    assert "<footer>Laptop · pytest &middot; Python " in body
    assert "&middot; Flask 3." in body


def test_redis_client_never_retries(monkeypatch):
    # redis-py 8 retries 10 times by default, which held a page for about a minute without Redis.
    monkeypatch.setenv("REDIS_HOST", "redis")
    module = importlib.reload(hello)
    try:
        assert module.redis is not None
        assert module.redis.get_retry().get_retries() == 0
    finally:
        monkeypatch.delenv("REDIS_HOST")
        importlib.reload(hello)
