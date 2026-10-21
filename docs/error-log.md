# Error log — Deployment Activity 4

Errors met while building and deploying, and how each was resolved (newest last).

| # | Date | Task | Error (exact message) | Cause | Fix |
|---|------|------|-----------------------|-------|-----|
| 1 | 2026-10-21 | Planning (Docker host) | `Error response from daemon: toomanyrequests: Rate exceeded` while `docker compose pull` fetched `postgres`, `redis` and two more images from `public.ecr.aws/docker/library/...` | Amazon ECR Public throttles anonymous pulls by IP; Compose pulls images in parallel | The Docker host pulls the official images from Docker Hub instead, and `deploy-app.ps1` runs `docker compose pull --policy missing`, so an image already on the host is never pulled again |
| 2 | 2026-10-21 | 4.4 Connect Four (listing 17) | `Names use 1-16 letters, digits, spaces, '_' or '-'.` for the first piped line `Ana`; the game then greeted `1` | Windows PowerShell prefixes data piped to a native program with a UTF-8 BOM (`EF BB BF`, checked with `od -c` in a container), so the first line read `U+FEFF` + `Ana` | The listing pipes the answers with Git Bash `printf` instead. Interactive play and the TCP client are unaffected |
