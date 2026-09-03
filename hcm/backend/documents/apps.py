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

    def ready(self):
        # HCM remediation H-3: registers this app's existing export
        # coverage as one domain in rbac_audit's subject-export registry,
        # rather than complete_export_request() being the whole export by
        # itself. Mirrors identity_verification's access_cascade
        # registration and recruitment's retention registration -- same
        # shape, different registry.
        from rbac_audit.subject_export import register

        from .services import _core_bundle_export_handler

        register("documents.core_bundle", _core_bundle_export_handler)
