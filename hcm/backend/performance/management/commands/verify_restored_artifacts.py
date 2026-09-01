from __future__ import annotations

import hashlib
import json

from django.core.management.base import BaseCommand, CommandError

from performance.models import AgreementDocument


def verify_signed_documents(documents) -> tuple[int, list[str]]:
    """Verify restored PDF bytes against document and signature hashes."""
    checked = 0
    problems: list[str] = []
    for document in documents:
        checked += 1
        try:
            digest = hashlib.sha256()
            with document.pdf.open("rb") as restored_file:
                for chunk in iter(lambda: restored_file.read(1024 * 1024), b""):
                    digest.update(chunk)
        except (FileNotFoundError, OSError) as exc:
            problems.append(f"document {document.pk}: media unavailable ({exc})")
            continue
        actual = digest.hexdigest()
        if actual != document.sha256:
            problems.append(f"document {document.pk}: restored media hash does not match document hash")
        for signature in document.signatures.all():
            if signature.document_sha256 != document.sha256:
                problems.append(f"document {document.pk}: signature {signature.pk} records a different hash")
    return checked, problems


class Command(BaseCommand):
    help = "Verify restored signed agreement PDFs against database hashes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-signed-document",
            action="store_true",
            help="Fail if the restored database contains no signed agreement document.",
        )

    def handle(self, *args, **options):
        documents = AgreementDocument.objects.filter(signatures__isnull=False).prefetch_related("signatures").distinct()
        checked, problems = verify_signed_documents(documents)
        result = {"signed_documents_checked": checked, "problems": problems}
        if options["require_signed_document"] and checked == 0:
            raise CommandError("No signed agreement document exists; database/media consistency is unproven.")
        if problems:
            raise CommandError(json.dumps(result, sort_keys=True))
        self.stdout.write(json.dumps(result, sort_keys=True))
