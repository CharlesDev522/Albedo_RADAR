#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os
import socket
import sys
import time
from urllib.parse import urlparse

raw = os.environ.get("DATABASE_URL", "postgresql+asyncpg://minerwatch:minerwatch@postgres:5432/minerwatch")
parsed = urlparse(raw.replace("postgresql+asyncpg", "postgresql"))
host = parsed.hostname or "postgres"
port = parsed.port or 5432

for attempt in range(1, 61):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"PostgreSQL ready at {host}:{port}", flush=True)
            sys.exit(0)
    except OSError as exc:
        if attempt == 60:
            print(f"PostgreSQL not ready at {host}:{port}: {exc}", file=sys.stderr, flush=True)
            sys.exit(1)
        time.sleep(2)
PY

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
