from django.core.management.base import BaseCommand, CommandError

from core_hr.imports import import_employees_csv, import_employees_xlsx


class Command(BaseCommand):
    help = "Bulk import employees from a CSV or Excel (.xlsx) file (Sprint 1)."

    def add_arguments(self, parser):
        parser.add_argument("file_path")

    def handle(self, *args, **options):
        path = options["file_path"]
        if path.lower().endswith(".xlsx"):
            with open(path, "rb") as f:
                result = import_employees_xlsx(f)
        elif path.lower().endswith(".csv"):
            with open(path, newline="", encoding="utf-8") as f:
                result = import_employees_csv(f)
        else:
            raise CommandError("File must be .csv or .xlsx")

        self.stdout.write(self.style.SUCCESS(f"Imported {result.imported_count} employee(s)."))
        if result.errors:
            self.stdout.write(self.style.WARNING(f"{result.error_count} row(s) skipped:"))
            for err in result.errors:
                self.stdout.write(f"  row {err.row_number} ({err.employee_number or '?'}): {err.reason}")
