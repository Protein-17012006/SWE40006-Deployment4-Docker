"""The footer line that proves where a screenshot was taken."""

import platform
import socket


def footer_text(app_version: str, deploy_target: str, pg_version: str | None) -> str:
    parts = [
        f"Quick Poll {app_version}",
        deploy_target,
        f"host {socket.gethostname()}",
        f"Python {platform.python_version()}",
    ]
    if pg_version:
        parts.append(f"PostgreSQL {pg_version}")
    return " · ".join(parts)
