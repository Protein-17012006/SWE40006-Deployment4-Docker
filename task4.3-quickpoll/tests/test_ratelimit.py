import fakeredis
from redis.exceptions import ConnectionError as RedisConnectionError

from quickpoll.ratelimit import RateLimiter


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class BrokenRedis:
    async def incr(self, key):
        raise RedisConnectionError("Error 111 connecting to redis:6379")


async def test_allows_up_to_the_limit_then_reports_seconds_left():
    clock = Clock(3600 * 10 + 600)                     # 10 minutes into the hour
    limiter = RateLimiter(fakeredis.FakeAsyncRedis(), clock)
    for _ in range(5):
        assert await limiter.hit("create", "1.2.3.4", 5, 3600) is None
    assert await limiter.hit("create", "1.2.3.4", 5, 3600) == 3000


async def test_each_ip_and_action_has_its_own_counter():
    limiter = RateLimiter(fakeredis.FakeAsyncRedis(), Clock(1000.0))
    for _ in range(5):
        await limiter.hit("create", "1.2.3.4", 5, 3600)
    assert await limiter.hit("create", "5.6.7.8", 5, 3600) is None
    assert await limiter.hit("vote", "1.2.3.4", 5, 3600) is None


async def test_a_new_window_starts_fresh():
    clock = Clock(59.0)
    limiter = RateLimiter(fakeredis.FakeAsyncRedis(), clock)
    assert await limiter.hit("vote", "ip", 1, 60) is None
    assert await limiter.hit("vote", "ip", 1, 60) == 1
    clock.now = 60.0
    assert await limiter.hit("vote", "ip", 1, 60) is None


async def test_keys_expire_with_the_window():
    redis = fakeredis.FakeAsyncRedis()
    await RateLimiter(redis, Clock(0.0)).hit("vote", "ip", 30, 60)
    assert 0 < await redis.ttl("quickpoll:rl:vote:ip:0") <= 60


async def test_fails_open_when_redis_is_down():
    assert await RateLimiter(BrokenRedis()).hit("vote", "ip", 1, 60) is None
