from django.apps import AppConfig


class CompensationConfig(AppConfig):
    name = 'compensation'

    def ready(self):
        # Data-quality handlers for this app's own checks (H3 org-wide
        # sweep) -- registered with the shared executor in core_hr, which
        # never imports a peer app. See compensation/data_quality.py.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import cycle_overdue_handler, stale_proposal_handler

        register(DataQualityException.ExceptionType.COMP_PROPOSAL_STALE, stale_proposal_handler)
        register(DataQualityException.ExceptionType.COMP_CYCLE_OVERDUE, cycle_overdue_handler)

        # HCM remediation H-3: this app's personal-data domain in
        # rbac_audit's subject-export registry.
        from rbac_audit.subject_export import register as register_export_handler

        from .subject_export import export_handler

        register_export_handler("compensation.CompProposal", export_handler)
