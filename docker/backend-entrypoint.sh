#!/bin/sh
set -eu

python - <<'PY'
import os
import socket
import sys
import time
import urllib.request
from urllib.parse import urlsplit


def wait_for_tcp(host: str, port: int, label: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"{label} is ready at {host}:{port}", flush=True)
                return
        except OSError as exc:
            last_error = exc
            time.sleep(2)
    print(f"Timed out waiting for {label}: {last_error}", file=sys.stderr, flush=True)
    sys.exit(1)


database_url = os.getenv("DATABASE_URL", "mysql+pymysql://root:root@db:3306/astra")
parsed_db = urlsplit(database_url.replace("mysql+pymysql://", "mysql://", 1))
db_host = parsed_db.hostname or "db"
db_port = parsed_db.port or 3306
wait_for_tcp(db_host, db_port, "MySQL")

qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
wait_for_tcp(qdrant_host, qdrant_port, "Qdrant TCP")

qdrant_url = f"http://{qdrant_host}:{qdrant_port}/collections"
deadline = time.time() + 120
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(qdrant_url, timeout=3) as response:
            if 200 <= response.status < 500:
                print(f"Qdrant HTTP is ready at {qdrant_url}", flush=True)
                break
    except Exception as exc:
        last_error = exc
        time.sleep(2)
else:
    print(f"Timed out waiting for Qdrant HTTP: {last_error}", file=sys.stderr, flush=True)
    sys.exit(1)
PY

exec uvicorn main:app --host 0.0.0.0 --port 8000
