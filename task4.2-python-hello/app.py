"""friendlyhello: the Flask "Hello World" web server from Docker's Get Started tutorial, modernised.

Visits are counted in Redis. Without Redis the page still works and says so, as in the tutorial.
"""

import html
import os
import platform
import socket
from importlib.metadata import version

from flask import Flask
from redis import Redis, RedisError
from redis.backoff import NoBackoff
from redis.retry import Retry

# Redis is optional. Without REDIS_HOST the counter is disabled at once, as in tutorial part 2.
# Retries are off: redis-py 8 retries by default, which held a request for about a minute when
# Redis was missing, longer than gunicorn's 30-second worker timeout.
REDIS_HOST = os.getenv("REDIS_HOST", "")
redis = Redis(
    host=REDIS_HOST,
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=0,
    socket_connect_timeout=2,
    socket_timeout=2,
    retry=Retry(NoBackoff(), 0),
) if REDIS_HOST else None

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>friendlyhello</title></head>
<body>
<h3>Hello {name}!</h3>
<b>Hostname:</b> {hostname}<br/>
<b>Visits:</b> {visits}
<hr>
<footer>{target} &middot; Python {python} &middot; Flask {flask}</footer>
</body>
</html>
"""


@app.route("/")
def hello():
    try:
        if redis is None:
            raise RedisError("REDIS_HOST is not set")
        visits = str(redis.incr("counter"))
    except RedisError:
        visits = "<i>cannot connect to Redis, counter disabled</i>"
    return PAGE.format(
        name=html.escape(os.getenv("NAME", "World")),
        hostname=html.escape(socket.gethostname()),
        visits=visits,
        target=html.escape(os.getenv("DEPLOY_TARGET", "Docker container")),
        python=platform.python_version(),
        flask=version("flask"),
    )


@app.route("/healthz")
def healthz():
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
