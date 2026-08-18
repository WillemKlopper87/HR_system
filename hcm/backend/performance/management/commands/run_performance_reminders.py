"""Emit today's performance-contracting reminders (PC-1, ADR-011).

    manage.py run_performance_reminders --dry-run   # what would go out today
    manage.py run_performance_reminders             # send + log
    manage.py run_performance_reminders --offset 14 # force the T-14 batch (testing/demo)
"""
from django.core.management.base import BaseCommand

from performance.models import PerformancePeriod
from performance.reminders import run_reminders


class Command(BaseCommand):
    help = "Push performance-contracting reminders for the open phase (collab work items, digests, announcements)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--period", help="period name, e.g. 2026/27 (default: whichever has an open phase)")
        parser.add_argument("--offset", type=int, help="force this reminder offset regardless of today's date")

    def handle(self, *args, **options):
        period = None
        if options["period"]:
            period = PerformancePeriod.objects.filter(name=options["period"]).first()
            if period is None:
                self.stderr.write(f"No period named {options['period']}")
                return
        run = run_reminders(period=period, dry_run=options["dry_run"], force_offset=options["offset"])
        mode = "dry-run" if run.dry_run else "sent"
        self.stdout.write(
            f"Performance reminders ({mode}): period={run.period or '—'} stage={run.stage or '—'} "
            f"offset={run.offset} outstanding={run.outstanding} items={run.items_sent} "
            f"digests={run.digests_sent} announcements={run.announcements_sent}"
        )
        if run.note:
            self.stdout.write(f"  {run.note}")
        for employee_number in run.skipped_no_collab_account[:20]:
            self.stdout.write(f"  skipped (no collab mapping): {employee_number}")
        for error in run.errors:
            self.stderr.write(f"  error: {error}")
