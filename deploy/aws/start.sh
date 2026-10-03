#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 deploy/aws/check_env.py .env.aws
chmod 600 .env.aws
python3 - <<'PY'
import os
from pathlib import Path
os.umask(0o077)
excluded = {'POSTGRES_PASSWORD', 'APP_USER_PASSWORD', 'API_DOMAIN', 'TLS_EMAIL'}
lines = [line for line in Path('.env.aws').read_text().splitlines()
         if '=' in line and not line.lstrip().startswith('#')
         and line.split('=', 1)[0].strip() not in excluded]
Path('.env.runtime').write_text('\n'.join(lines) + '\n')
os.chmod('.env.runtime', 0o600)
PY
dc=(docker compose --env-file .env.aws -f compose.production.yaml)
"${dc[@]}" config --quiet
if [[ "${1:-}" == '--prepare-only' ]]; then
  echo 'Environment prepared. API and workers have not been started.'
  exit 0
fi
# Run as root or as an operator with Docker permissions on the dedicated VM.
mkdir -p /opt/gradewise/sandbox
chmod 700 /opt/gradewise/sandbox
"${dc[@]}" build api
"${dc[@]}" up -d --wait --wait-timeout 180 postgres redis
# Safe on both fresh and restored databases; init scripts only run on empty volumes.
"${dc[@]}" exec -T postgres psql -U feedback -d feedback -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/10_app_role.sql
"${dc[@]}" run --rm --no-deps api python -c 'import asyncio, os, asyncpg; asyncio.run(asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")))'
# These are the existing runner's image names; pull before any code-grading jobs.
docker pull python:3.10-slim
docker pull gcc:latest
docker pull eclipse-temurin:17-jdk
"${dc[@]}" up -d --wait --wait-timeout 240 api worker beat caddy
curl --fail --silent --show-error http://127.0.0.1:8000/health
"${dc[@]}" exec -T worker celery -A app.workers.celery_app inspect ping --timeout 10
echo 'Local API and worker checks passed. Verify public HTTPS and a real grading job before frontend cutover.'
