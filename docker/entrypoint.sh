#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Wait for PostgreSQL to be ready before running migrations (F-13)
# Uses Python (always available) to avoid needing pg_isready in the image.
# ---------------------------------------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
  python - <<'PYEOF'
import os, socket, sys, time
from urllib.parse import urlsplit

url = urlsplit(os.environ.get("DATABASE_URL", ""))
host = url.hostname or "localhost"
port = url.port or 5432
max_attempts = 30

for attempt in range(1, max_attempts + 1):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f"[entrypoint] PostgreSQL ready at {host}:{port}")
        sys.exit(0)
    except OSError:
        print(f"[entrypoint] Waiting for PostgreSQL at {host}:{port} ({attempt}/{max_attempts})...")
        time.sleep(1)

print(f"[entrypoint] PostgreSQL not ready after {max_attempts}s, aborting.")
sys.exit(1)
PYEOF
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
fi

if [ $# -gt 0 ]; then
  exec "$@"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

