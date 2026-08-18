"""Resolve collab-platform ids for employees (by work email) and departments (by name).

    manage.py sync_collab_ids --dry-run     # report what would be mapped
    manage.py sync_collab_ids               # write Employee.collab_user_id / Department.collab_department_id
    manage.py sync_collab_ids --all         # re-check rows that already have an id
"""
from django.core.management.base import BaseCommand, CommandError

from integrations import collab
from integrations.sync import sync_collab_ids


class Command(BaseCommand):
    help = "Map HCM employees/departments to their collab-platform ids (ADR-011)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--all", action="store_true", help="re-resolve rows that already have an id")

    def handle(self, *args, **options):
        client = collab.get_client()
        if client is None:
            raise CommandError("Collab integration is disabled or unconfigured (COLLAB_ENABLED / COLLAB_BASE_URL / COLLAB_API_KEY).")
        try:
            result = sync_collab_ids(client, dry_run=options["dry_run"], only_missing=not options["all"])
        finally:
            client.close()
        mode = "dry-run" if result.dry_run else "written"
        self.stdout.write(
            f"Collab id sync ({mode}): departments matched={result.departments_matched} "
            f"unmatched={len(result.departments_unmatched)}; employees matched={result.employees_matched} "
            f"unmatched={len(result.employees_unmatched)}"
        )
        for name in result.departments_unmatched:
            self.stdout.write(f"  department not found in collab: {name}")
        for email in result.employees_unmatched[:50]:
            self.stdout.write(f"  no collab user for: {email}")
        if len(result.employees_unmatched) > 50:
            self.stdout.write(f"  … and {len(result.employees_unmatched) - 50} more")
