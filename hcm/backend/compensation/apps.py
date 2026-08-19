from django.apps import AppConfig


class CompensationConfig(AppConfig):
    name = 'compensation'

    def ready(self):
        # Data-quality handler for this app's own stale-proposal check
        # (H3 org-wide sweep) -- registered with the shared executor in
        # core_hr, which never imports a peer app. See compensation/data_quality.py.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import stale_proposal_handler

        register(DataQualityException.ExceptionType.COMP_PROPOSAL_STALE, stale_proposal_handler)
