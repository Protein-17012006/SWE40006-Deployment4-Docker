# syntax=docker/dockerfile:1
# Connect Four (SWE40006 Task 4.4). Standard library only, so alpine keeps the image small.

# ---- test: the build fails if any test fails ----
FROM python:3.14-alpine AS test
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN python -m pytest -q -p no:cacheprovider

# ---- runtime: no third-party packages at all ----
FROM python:3.14-alpine AS runtime
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="connect4" \
      org.opencontainers.image.description="Connect Four console game and TCP server - SWE40006 Task 4.4" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Protein-17012006/SWE40006-Deployment4-Docker"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
WORKDIR /app
COPY connect4 ./connect4
# /data belongs to the app user, so new volumes mounted there are writable by it.
RUN adduser -D -u 10001 app && mkdir /data && chown app:app /data
USER 10001
VOLUME ["/data"]
EXPOSE 2323
ENTRYPOINT ["python", "-m", "connect4"]
CMD ["play"]
