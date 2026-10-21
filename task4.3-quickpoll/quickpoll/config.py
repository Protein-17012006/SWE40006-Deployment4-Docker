"""Settings from environment variables (Compose `environment:`, filled from `.env` on the laptop and on the Docker host)."""

import os
from dataclasses import dataclass
from typing import Mapping

from psycopg.conninfo import make_conninfo


@dataclass(frozen=True)
class Settings:
    database_host: str = "postgres"
    database_port: int = 5432
    database_name: str = "quickpoll"
    database_user: str = "quickpoll"
    database_password: str = ""
    redis_url: str = "redis://redis:6379/0"
    deploy_target: str = "Docker container"
    app_version: str = "dev"

    def conninfo(self, connect_timeout: int = 3) -> str:
        """A libpq connection string; make_conninfo quotes any special characters safely."""
        return make_conninfo(
            host=self.database_host,
            port=self.database_port,
            dbname=self.database_name,
            user=self.database_user,
            password=self.database_password,
            connect_timeout=connect_timeout,
            application_name="quickpoll",
        )


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    return Settings(
        database_host=env.get("DATABASE_HOST", "postgres"),
        database_port=int(env.get("DATABASE_PORT", "5432")),
        database_name=env.get("DATABASE_NAME", "quickpoll"),
        database_user=env.get("DATABASE_USER", "quickpoll"),
        database_password=env.get("DATABASE_PASSWORD", ""),
        redis_url=env.get("REDIS_URL", "redis://redis:6379/0"),
        deploy_target=env.get("DEPLOY_TARGET", "Docker container"),
        app_version=env.get("APP_VERSION", "dev"),
    )
