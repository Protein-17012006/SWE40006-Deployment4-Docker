# Error log — Deployment Activity 4

Errors met while building and deploying, and how each was resolved (newest last).

| # | Date | Task | Error (exact message) | Cause | Fix |
|---|------|------|-----------------------|-------|-----|
| 1 | 2026-10-21 | Planning (Docker host) | `Error response from daemon: toomanyrequests: Rate exceeded` while `docker compose pull` fetched `postgres`, `redis` and two more images from `public.ecr.aws/docker/library/...` | Amazon ECR Public throttles anonymous pulls by IP; Compose pulls images in parallel | The Docker host pulls the official images from Docker Hub instead, and `deploy-app.ps1` runs `docker compose pull --policy missing`, so an image already on the host is never pulled again |
