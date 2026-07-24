#!/usr/bin/env bash
set -euo pipefail
mkdir -p "${DATA_DIR:-/var/data}"
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-10000}" --workers "${WEB_WORKERS:-1}" --proxy-headers
