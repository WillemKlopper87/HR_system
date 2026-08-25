from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Employee documents (tiered, consent-aware, authenticated download)
    and the POPIA data-subject export/erasure request workflow (C2 —
    docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md).
    A new peer app, not folded into core_hr (SHARED_KERNEL, must not
    accrete file-storage/consent-workflow logic) or policies (whose whole
    shape is an org-wide broadcast document, not a private per-employee
    file) — see the spec §2.1."""

    name = "documents"
    verbose_name = "Employee documents & POPIA rights (C2)"
