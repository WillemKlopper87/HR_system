#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/hcm-backup-<id>" >&2
  exit 2
fi
backup_dir="$(realpath "$1")"
if [[ ! -d "$backup_dir" || "$(basename "$backup_dir")" != hcm-backup-* ]]; then
  echo "Backup directory must exist and have an hcm-backup-* name" >&2
  exit 2
fi
for required in database.dump media.tar.gz SHA256SUMS manifest.txt; do
  [[ -f "$backup_dir/$required" ]] || { echo "Missing $required" >&2; exit 2; }
done
(
  cd "$backup_dir"
  sha256sum -c SHA256SUMS
)

backup_id="$(sed -n 's/^backup_id=//p' "$backup_dir/manifest.txt")"
[[ "$backup_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid backup_id in manifest" >&2; exit 2; }
project="hcm-restore-${backup_id,,}-$$"
project="${project//./-}"
keep="${HCM_RESTORE_KEEP_ENVIRONMENT:-false}"
cleanup() {
  if [[ "$keep" != "true" ]]; then
    docker compose -p "$project" down -v --remove-orphans >/dev/null 2>&1 || true
  else
    echo "Isolated restore retained as Compose project: $project" >&2
  fi
}
trap cleanup EXIT

if [[ -n "$(docker compose -p "$project" ps -q 2>/dev/null)" ]]; then
  echo "Refusing to reuse existing Compose project $project" >&2
  exit 3
fi

docker compose -p "$project" up -d --wait db redis
docker compose -p "$project" exec -T db sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$backup_dir/database.dump"
docker compose -p "$project" run --rm --no-deps -T backend tar -xzf - -C /app/media \
  < "$backup_dir/media.tar.gz"
docker compose -p "$project" up -d --wait backend
docker compose -p "$project" exec -T backend python manage.py verify_restored_artifacts --require-signed-document
docker compose -p "$project" exec -T backend python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=10) as response:
    payload = json.load(response)
    if response.status != 200 or payload.get("status") != "ready":
        raise SystemExit(f"readiness failed: {response.status} {payload}")
PY

echo "Isolated restore verified successfully: $project"
