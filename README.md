# Docker containers — SWE40006 Deployment Activity 4

Three Python apps packaged with Docker, published to Docker Hub, and run on a second Docker device:
an Amazon EC2 instance with Docker Engine and Docker Compose. friendlyhello was first pulled and run there by hand;
every app now runs as a Compose project. The Docker host itself is defined in AWS CloudFormation.

| Sub-task | App | Try it |
|---|---|---|
| 4.1 | `hello-world` on Docker Desktop | `docker run hello-world` |
| 4.2 | **friendlyhello** — Flask web server with a Redis visit counter (Docker's Get Started app) | http://52.220.44.53:4000/ · `docker run -p 4000:80 emtrai/friendlyhello` |
| 4.3 | **Quick Poll** — create a poll, share it, watch results update live (FastAPI, PostgreSQL 18, Redis 8, nginx) | http://52.220.44.53/ |
| 4.4 | **Connect Four** — a terminal game against the CPU, played over TCP | `nc 52.220.44.53 2323` · `docker run -it --rm emtrai/connect4 client 52.220.44.53` · offline: `docker run -it --rm emtrai/connect4` |

Images (public): [friendlyhello](https://hub.docker.com/r/emtrai/friendlyhello) ·
[quickpoll](https://hub.docker.com/r/emtrai/quickpoll) ·
[quickpoll-proxy](https://hub.docker.com/r/emtrai/quickpoll-proxy) ·
[connect4](https://hub.docker.com/r/emtrai/connect4)

## Architecture

- **Docker device #1:** a Windows 11 laptop with Docker Desktop (builds, tests, pushes).
- **Docker device #2:** one EC2 `t3.small` running Amazon Linux 2023, with Docker Engine 25 and the Docker Compose v5.6.0 plugin,
  and an Elastic IP, in `ap-southeast-1`. Every container on it was started by `docker` or `docker compose`.
- **Compose projects on the host** (`/opt/swe40006-a4/<project>`): `hello` (:4000), `quickpoll` (:80; proxy, web, migrate,
  postgres, redis) and `connect4` (:2323). Each runs the app's `compose.deploy.yaml`, which pulls the published images.
- **CloudFormation stack** `swe40006-a4-docker-host`: VPC, security group, an instance role for Session Manager only,
  the instance and its Elastic IP. The instance installs Docker at first boot and signals CloudFormation when Docker works.
- **No SSH:** the host is managed through AWS Systems Manager. Only ports 80, 4000 and 2323 are open.

## Repository layout

| Path | Contents |
|---|---|
| `infra/cfn/docker-host.yaml` | CloudFormation template of the Docker host |
| `infra/*.ps1` | `deploy-stack.ps1` (lint → validate → change set → execute), `push-image.ps1`, `deploy-app.ps1`, `run-on-instance.ps1`, `check-live.ps1`, `teardown.ps1`, `config.ps1` |
| `task4.2-python-hello/` | friendlyhello: `app.py`, tests, `Dockerfile` (`python:3.14-slim`), `compose.yaml`, `compose.deploy.yaml` |
| `task4.3-quickpoll/` | Quick Poll: `quickpoll/` package, SQL `migrations/`, `proxy/` (nginx), multi-stage `Dockerfile`, `compose.yaml`, `compose.deploy.yaml`, `compose.test.yaml`, tests |
| `task4.4-connect4/` | Connect Four: `connect4/` package (standard library only), tests, `Dockerfile` (`python:3.14-alpine`), `compose.yaml`, `compose.deploy.yaml` |
| `docs/` | Architecture diagram (`architecture.drawio`) and error log |

## Run the tests

```powershell
# friendlyhello (9 tests) and Connect Four (80 tests): one virtual environment each
cd task4.2-python-hello; py -3.14 -m venv .venv; .venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt; .venv\Scripts\python -m pytest; cd ..
cd task4.4-connect4; py -3.14 -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt; .venv\Scripts\python -m pytest; cd ..
# Quick Poll (89 tests, PostgreSQL included) runs in Linux containers
cd task4.3-quickpoll; docker compose -f compose.test.yaml run --rm --build tests; cd ..
```

## Run locally from source

```powershell
docker compose -f task4.2-python-hello/compose.yaml up -d          # http://localhost:4000
copy task4.3-quickpoll\.env.example task4.3-quickpoll\.env         # then set POSTGRES_PASSWORD
docker compose -f task4.3-quickpoll/compose.yaml up -d --build     # http://127.0.0.1:8090
docker compose -f task4.4-connect4/compose.yaml up -d --build      # nc 127.0.0.1 2323
```

## Run the published images on any Docker device

Put an `.env` next to a `compose.deploy.yaml` (for example `DOCKERHUB_USER=emtrai`, `TAG=1.0.0`), then run `docker compose -f compose.deploy.yaml up -d --wait`.
Quick Poll needs `WEB_TAG`, `PROXY_TAG` and `POSTGRES_PASSWORD`.

## Deploy, update, clean up (AWS CLI profile `swe40006-a2`)

```powershell
.\infra\deploy-stack.ps1                                   # creates a change set and prints it
.\infra\deploy-stack.ps1 -Execute                          # applies it: the Docker host
.\infra\push-image.ps1 -App quickpoll -Tag 1.1.0           # Docker Hub
.\infra\deploy-app.ps1 -App quickpoll -Tag 1.1.0           # pull, up --dry-run, up --wait on the host
.\infra\check-live.ps1                                     # the four public endpoints
.\infra\teardown.ps1 -DryRun                               # after grading, then without -DryRun
```

The report with screenshots is submitted separately on Canvas.
