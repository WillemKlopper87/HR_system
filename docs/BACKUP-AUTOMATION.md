# Automated backup and isolated restore verification

The repository now contains provider-neutral operational tooling under `hcm/ops/`. It prepares and verifies database
and media backups without pretending that the repository can provision the organisation's off-site storage, production
host, encryption keys, monitoring, or recovery ownership.

## Nightly backup

`backup.sh` creates a PostgreSQL custom-format dump and a media archive, writes a manifest and SHA-256 checksum file,
verifies them locally, atomically copies the completed directory to a separately mounted off-site target, verifies the
copy again, and applies bounded retention only to exact `hcm-backup-*` child directories.

Required `/etc/hcm/backup.env` values for the supplied systemd unit:

```text
HCM_BACKUP_DIR=/var/backups/hcm
HCM_BACKUP_OFFSITE_DIR=/mnt/hcm-offsite
HCM_BACKUP_RETENTION_DAYS=35
```

`HCM_BACKUP_OFFSITE_DIR` must be storage with a separate failure domain, mounted and encrypted according to the hosting
decision. A second local directory does not meet the off-site requirement. Install the service/timer files from
`hcm/ops/systemd/`, adjust `/opt/hcm/current` and the service account to the production layout, then enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hcm-backup.timer
systemctl list-timers hcm-backup.timer
```

Alert externally if the service fails or if no new verified directory appears in the off-site target inside the agreed
window. Repository code cannot establish that alert destination without an operations-provider decision.

## Isolated restore rehearsal

From `hcm/`, run against a selected completed backup:

```bash
ops/restore-verify.sh /mnt/hcm-offsite/hcm-backup-YYYYMMDDTHHMMSSZ-<git-sha>
```

The verifier checks archive hashes before starting, creates a unique Compose project with fresh database/media volumes,
restores both archives, runs migrations, waits for application readiness, and runs
`manage.py verify_restored_artifacts --require-signed-document`. That command reads restored signed agreement PDFs and
checks their bytes against both the document hash and every linked signature hash. The isolated project and volumes are
removed on exit; set `HCM_RESTORE_KEEP_ENVIRONMENT=true` only when an authorised rehearsal needs inspection.

This is stronger than merely proving that `pg_restore` exits successfully: it verifies a database record and its media
artifact are mutually consistent. A rehearsal still needs dated evidence of its duration, operator, backup age,
environment, result, and the approved RPO/RTO decision.

## Evidence boundary

The scripts and unit tests prove repository behavior. They do not prove that systemd is installed/enabled on a live
host, the target is genuinely off-site, backups are encrypted, monitoring alerts fire, or a production-data rehearsal
has happened. Keep those checklist items open until operations supplies authoritative evidence.
