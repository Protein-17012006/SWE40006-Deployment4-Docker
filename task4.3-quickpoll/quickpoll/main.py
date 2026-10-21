"""FastAPI application factory, routes and error pages.

Run with:  uvicorn quickpoll.main:create_app --factory --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import security
from .config import Settings, load_settings
from .hostinfo import footer_text
from .live import LiveUpdates, event_stream, utcnow
from .ratelimit import RateLimiter
from .repository import DatabaseUnavailable, InvalidOption, PollRepository
from .validation import CLOSE_AFTER, OPTIONS_MAX, parse_option_id, validate_poll

log = logging.getLogger("quickpoll")


def configure_logging() -> None:
    """Send the app's own INFO messages to stdout (uvicorn only configures its own loggers)."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=HERE / "templates")

SLUG_PATTERN = re.compile(r"[A-Za-z0-9]{1,12}")
CREATE_LIMIT = (5, 3600)   # polls per IP per hour
VOTE_LIMIT = (30, 60)      # votes per IP per minute

CLOSE_CHOICES = [("never", "Never"), ("1h", "1 hour"), ("1d", "1 day"), ("7d", "7 days")]


def close_status(poll, now: datetime) -> str | None:
    """'Closes on ...' / 'Closed on ...' in UTC, or None for a poll that never closes."""
    if poll.closes_at is None:
        return None
    when = poll.closes_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Closed on {when}" if poll.is_closed(now) else f"Closes on {when}"


def create_app(settings: Settings | None = None, repo=None, redis=None, clock=utcnow) -> FastAPI:
    """Build the app. Tests pass a fake `repo` and `redis`; in production the lifespan creates them."""
    settings = settings or load_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        closers = []
        if app.state.repo is None:
            pool = AsyncConnectionPool(settings.conninfo(), min_size=1, max_size=5, open=False, timeout=3)
            await pool.open(wait=False)          # start even if PostgreSQL is not up yet
            app.state.repo = PollRepository(pool)
            closers.append(pool.close)
        if app.state.redis is None:
            # No retries: when Redis is down every call must fail fast so the app can fail open.
            app.state.redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1,
                                             retry=Retry(NoBackoff(), 0))
            closers.append(app.state.redis.aclose)
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.live = LiveUpdates(app.state.redis)
        yield
        for close in reversed(closers):
            await close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.repo = repo
    app.state.redis = redis
    app.state.limiter = RateLimiter(redis) if redis is not None else None
    app.state.live = LiveUpdates(redis) if redis is not None else None
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    # ---------- helpers ----------

    def client_ip(request: Request) -> str:
        # nginx overwrites X-Real-IP; the app port is never published, so only nginx can set it.
        return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")

    async def render(request: Request, template: str, context: dict, status_code: int = 200,
                     headers: dict | None = None) -> HTMLResponse:
        token = request.cookies.get(security.CSRF_COOKIE)
        fresh = not security.looks_like_token(token)
        if fresh:
            token = security.new_csrf_token()
        pg_version = await app.state.repo.server_version() if app.state.repo is not None else None
        context = {
            **context,
            "csrf_field": security.CSRF_FIELD,
            "csrf_token": token,
            "footer": footer_text(settings.app_version, settings.deploy_target, pg_version),
        }
        response = templates.TemplateResponse(request, template, context, status_code=status_code, headers=headers)
        if fresh:
            response.set_cookie(security.CSRF_COOKIE, token, httponly=True, samesite="lax")
        return response

    async def error_page(request: Request, status_code: int, message: str, headers: dict | None = None):
        return await render(request, "error.html", {"status": status_code, "message": message},
                            status_code=status_code, headers=headers)

    async def read_form(request: Request):
        try:
            return await request.form(max_files=0, max_fields=20, max_part_size=16 * 1024)
        except Exception:  # malformed body or wrong content type: treat as an empty form
            return {}

    def form_values(form, name: str) -> list:
        return form.getlist(name) if hasattr(form, "getlist") else []

    async def find_poll(slug: str):
        if not SLUG_PATTERN.fullmatch(slug):
            raise StarletteHTTPException(404)
        poll = await app.state.repo.get_poll(slug)
        if poll is None:
            raise StarletteHTTPException(404)
        return poll

    # ---------- pages ----------

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return await render(request, "home.html", {"form": None, "errors": {}, "option_slots": OPTIONS_MAX, "close_choices": CLOSE_CHOICES})

    @app.post("/polls")
    async def create_poll(request: Request):
        form = await read_form(request)
        if not security.csrf_valid(request.cookies.get(security.CSRF_COOKIE), form.get(security.CSRF_FIELD)):
            return await error_page(request, 400, "Form expired, please reload the page and try again.")
        retry_after = await app.state.limiter.hit("create", client_ip(request), *CREATE_LIMIT)
        if retry_after:
            return await error_page(request, 429, "Too many new polls from your address. Please try again later.",
                                    headers={"Retry-After": str(retry_after)})
        poll_input = validate_poll(form.get("question"), form_values(form, "option"),
                                   form.get("close_after", "never"))
        if not poll_input.ok:
            return await render(request, "home.html",
                                {"form": poll_input, "errors": poll_input.errors, "option_slots": OPTIONS_MAX,
                                 "close_choices": CLOSE_CHOICES},
                                status_code=422)
        delta = CLOSE_AFTER[poll_input.close_after]
        closes_at = clock() + delta if delta else None
        poll = await app.state.repo.create_poll(poll_input.question, poll_input.options, closes_at)
        log.info("poll %s created with %d options", poll.slug, len(poll.options))
        return RedirectResponse(f"/p/{poll.slug}", status_code=303)

    @app.get("/p/{slug}", response_class=HTMLResponse)
    async def vote_page(request: Request, slug: str):
        poll = await find_poll(slug)
        voter = security.parse_voter_id(request.cookies.get(security.VOTER_COOKIE))
        if voter is not None and await app.state.repo.has_voted(poll.id, voter):
            return RedirectResponse(f"/p/{poll.slug}/results", status_code=303)
        now = clock()
        return await render(request, "vote.html", {"poll": poll, "error": None, "closed": poll.is_closed(now),
                                                   "close_text": close_status(poll, now)})

    @app.post("/p/{slug}/vote")
    async def vote(request: Request, slug: str):
        poll = await find_poll(slug)
        form = await read_form(request)
        if not security.csrf_valid(request.cookies.get(security.CSRF_COOKIE), form.get(security.CSRF_FIELD)):
            return await error_page(request, 400, "Form expired, please reload the page and try again.")
        retry_after = await app.state.limiter.hit("vote", client_ip(request), *VOTE_LIMIT)
        if retry_after:
            return await error_page(request, 429, "Too many votes from your address. Please wait a minute.",
                                    headers={"Retry-After": str(retry_after)})
        if poll.is_closed(clock()):
            return RedirectResponse(f"/p/{poll.slug}/results?closed=1", status_code=303)
        option_id = parse_option_id(form.get("option"))
        if option_id is None or not poll.has_option(option_id):
            return await render(request, "vote.html", {"poll": poll, "error": "Choose one of the options.", "closed": False, "close_text": close_status(poll, clock())},
                                status_code=422)
        voter = security.parse_voter_id(request.cookies.get(security.VOTER_COOKIE)) or uuid.uuid4()
        try:
            recorded = await app.state.repo.record_vote(poll.id, option_id, voter)
        except InvalidOption:
            return await render(request, "vote.html", {"poll": poll, "error": "Choose one of the options.", "closed": False, "close_text": close_status(poll, clock())},
                                status_code=422)
        if recorded:
            await app.state.live.publish(poll.id)
        target = f"/p/{poll.slug}/results" + ("" if recorded else "?already=1")
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(security.VOTER_COOKIE, str(voter), max_age=security.VOTER_MAX_AGE,
                            httponly=True, samesite="lax")
        return response

    @app.get("/p/{slug}/results", response_class=HTMLResponse)
    async def results_page(request: Request, slug: str, already: str | None = None, closed: str | None = None):
        poll = await find_poll(slug)
        results = await app.state.repo.results(poll)
        notice = "This poll is closed." if closed else ("You already voted in this poll." if already else None)
        share_url = str(request.url_for("vote_page", slug=poll.slug))
        return await render(request, "results.html",
                            {"poll": poll, "results": results, "notice": notice, "share_url": share_url,
                             "close_text": close_status(poll, clock())})

    @app.get("/p/{slug}/events")
    async def results_events(slug: str):
        poll = await find_poll(slug)
        return StreamingResponse(
            event_stream(poll, app.state.repo, app.state.live, now=clock),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    @app.get("/readyz")
    async def readyz():
        checks = {}
        try:
            await asyncio.wait_for(app.state.repo.ping(), 1.0)
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"
        try:
            await asyncio.wait_for(app.state.redis.ping(), 1.0)
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
        ready = all(value == "ok" for value in checks.values())
        return JSONResponse({"status": "ok" if ready else "unavailable", **checks}, status_code=200 if ready else 503)

    # ---------- errors ----------

    @app.exception_handler(DatabaseUnavailable)
    async def database_unavailable(request: Request, exc: DatabaseUnavailable):
        log.error("database unavailable: %s", exc)
        return await error_page(request, 503, "Polls are temporarily unavailable. Please try again in a minute.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        messages = {404: "That page or poll does not exist.", 405: "That action is not allowed here."}
        return await error_page(request, exc.status_code, messages.get(exc.status_code, "The request was not valid."))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return await error_page(request, 500, "Something went wrong on our side. Please try again.")

    return app
