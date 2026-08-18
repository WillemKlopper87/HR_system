from django.apps import AppConfig


class RecruitmentConfig(AppConfig):
    name = 'recruitment'

    def ready(self):
        # Register this app's retention handler with the shared executor
        # (rbac_audit/retention.py) — the executor never imports peer apps.
        from rbac_audit.retention import register

        from .retention import applicant_retention_handler

        register("recruitment.Applicant", applicant_retention_handler)
