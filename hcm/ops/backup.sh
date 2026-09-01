#!/usr/bin/env bash
set -Eeuo pipefail

# Provider-neutral backup runner. HCM_BACKUP_OFFSITE_DIR must be a separately
# mounted target (NFS, encrypted removable storage, or an object-store FUSE
# mount); a second directory on the application host is not off-site.
: "${HCM_BACKUP_DIR:?set HCM_BACKUP_DIR to the local staging directory}"
: "${HCM_BACKUP_OFFSITE_DIR:?set HCM_BACKUP_OFFSITE_DIR to a separately mounted off-site target}"

HCM_BACKUP_RETENTION_DAYS="${HCM_BACKUP_RETENTION_DAYS:-35}"
case "$HCM_BACKUP_RETENTION_DAYS" in
  ''|*[!0-9]*) echo "HCM_BACKUP_RETENTION_DAYS must be a non-negative integer" >&2; exit 2 ;;
esac

mkdir -p -- "$HCM_BACKUP_DIR" "$HCM_BACKUP_OFFSITE_DIR"
local_dir="$(realpath "$HCM_BACKUP_DIR")"
offsite_dir="$(realpath "$HCM_BACKUP_OFFSITE_DIR")"
if [[ "$local_dir" == "/" || "$offsite_dir" == "/" || "$local_dir" == "$offsite_dir" ]]; then
  echo "Backup targets must be distinct directories and must not resolve to /" >&2
  exit 2
fi
if ! mountpoint -q -- "$offsite_dir"; then
  echo "HCM_BACKUP_OFFSITE_DIR must itself be a mounted separate-failure-domain target" >&2
  exit 2
fi

lock_dir="$local_dir/.hcm-backup.lock"
if ! mkdir -- "$lock_dir" 2>/dev/null; then
  echo "Another HCM backup is already running ($lock_dir exists)" >&2
  exit 3
fi
stage_dir=""
offsite_stage=""
cleanup() {
  [[ -z "$stage_dir" || ! -d "$stage_dir" ]] || rm -r -- "$stage_dir"
  [[ -z "$offsite_stage" || ! -d "$offsite_stage" ]] || rm -r -- "$offsite_stage"
  rmdir -- "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

backup_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short=12 HEAD 2>/dev/null || printf unknown)"
stage_dir="$(mktemp -d "$local_dir/.hcm-backup-${backup_id}.XXXXXX")"
final_dir="$local_dir/hcm-backup-$backup_id"
offsite_stage="$offsite_dir/.hcm-backup-$backup_id.incoming"
offsite_final="$offsite_dir/hcm-backup-$backup_id"
if [[ -e "$final_dir" || -e "$offsite_stage" || -e "$offsite_final" ]]; then
  echo "Refusing to overwrite an existing backup for $backup_id" >&2
  exit 4
fi

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
  > "$stage_dir/database.dump"
docker compose exec -T backend tar -czf - -C /app/media . > "$stage_dir/media.tar.gz"

(
  cd "$stage_dir"
  sha256sum database.dump media.tar.gz > SHA256SUMS
  cat > manifest.txt <<EOF
format_version=1
backup_id=$backup_id
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
git_commit=$(git rev-parse HEAD 2>/dev/null || printf unknown)
database_format=postgres_custom
media_format=tar_gzip
EOF
  sha256sum manifest.txt >> SHA256SUMS
  sha256sum -c SHA256SUMS
)

mv -- "$stage_dir" "$final_dir"
stage_dir=""
cp -a -- "$final_dir" "$offsite_stage"
(
  cd "$offsite_stage"
  sha256sum -c SHA256SUMS
)
mv -- "$offsite_stage" "$offsite_final"
offsite_stage=""

# Retention is constrained to exact hcm-backup-* child directories beneath
# the two validated roots. The current backup cannot match the age filter.
find "$local_dir" -mindepth 1 -maxdepth 1 -type d -name 'hcm-backup-*' -mtime "+$HCM_BACKUP_RETENTION_DAYS" -print -exec rm -r -- {} \;
find "$offsite_dir" -mindepth 1 -maxdepth 1 -type d -name 'hcm-backup-*' -mtime "+$HCM_BACKUP_RETENTION_DAYS" -print -exec rm -r -- {} \;

echo "Backup complete and off-site copy verified: $offsite_final"
