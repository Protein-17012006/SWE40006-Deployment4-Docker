# syntax=docker/dockerfile:1
# nginx-unprivileged runs as uid 101 and listens on 8080 (the host maps port 80 to it).
FROM nginxinc/nginx-unprivileged:1.30-alpine
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="quickpoll-proxy" \
      org.opencontainers.image.description="nginx reverse proxy for Quick Poll - SWE40006 Task 4.3" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Protein-17012006/SWE40006-Deployment4-Docker"
COPY default.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
