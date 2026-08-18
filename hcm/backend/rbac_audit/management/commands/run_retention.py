"""Run the retention rules once, from the shell (no Celery needed).

    manage.py run_retention --dry-run   # report what would be affected
    manage.py run_retention             # execute + audit-log
"""
from django.core.management.base import BaseCommand

from rbac_audit import retention


class Command(BaseCommand):
    help = "Execute active RetentionRule rows through their registered handlers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing, log nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        results = retention.run_retention(dry_run=dry_run)
        mode = "dry-run" if dry_run else "executed"
        self.stdout.write(f"Retention {mode}: {len(results)} rule(s); handlers registered for: "
                          f"{', '.join(retention.registered_entity_types()) or '(none)'}")
        for r in results:
            cutoff = r.cutoff.date().isoformat() if r.cutoff else "-"
            line = f"  {r.entity_type:<40} {r.action:<10} cutoff={cutoff:<10} {r.status:<10} affected={r.affected}"
            if r.detail:
                line += f"  ({r.detail})"
            self.stdout.write(line)
