#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077
backup_dir="${1:?Usage: bash deploy/aws/backup.sh /absolute/backup/directory}"
[[ "$backup_dir" = /* ]] || { echo 'Backup path must be absolute'; exit 1; }
mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dc=(docker compose --env-file .env.aws -f compose.production.yaml)
# Maintenance window: freeze writes so the DB and uploaded files are consistent.
# Always resume services, including when an export fails.
trap '"${dc[@]}" start api worker beat caddy' EXIT
"${dc[@]}" stop caddy api beat worker
"${dc[@]}" exec -T postgres pg_dump -U feedback -d feedback -Fc > "$backup_dir/$stamp-postgres.dump.partial"
mv "$backup_dir/$stamp-postgres.dump.partial" "$backup_dir/$stamp-postgres.dump"
"${dc[@]}" run --rm --no-deps api tar -C /app/uploads -czf - . > "$backup_dir/$stamp-uploads.tar.gz.partial"
mv "$backup_dir/$stamp-uploads.tar.gz.partial" "$backup_dir/$stamp-uploads.tar.gz"
echo 'Backup complete. Copy both files off this VM and protect them as student data.'
