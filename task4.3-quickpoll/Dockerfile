# syntax=docker/dockerfile:1

# ---- base: Python runtime + pinned dependencies ----
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- test: the unit and route tests must pass for the build to succeed ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN python -m pytest -q -m "not db" -p no:cacheprovider

# ---- runtime: only the app, as an unprivileged user ----
FROM base AS runtime
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="quickpoll" \
      org.opencontainers.image.description="Quick Poll web app (FastAPI, PostgreSQL, Redis) - SWE40006 Task 4.3" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Protein-17012006/SWE40006-Deployment4-Docker"
ENV APP_VERSION=${APP_VERSION}
COPY quickpoll ./quickpoll
COPY migrations ./migrations
RUN useradd --create-home --uid 10001 app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "quickpoll.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
