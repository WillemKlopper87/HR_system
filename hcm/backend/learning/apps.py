from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = 'learning'

    def ready(self):
        # Data-quality handler for this app's own overdue-mandatory-
        # training check (H3 org-wide sweep, C6) -- registered with the
        # shared executor in core_hr, which never imports a peer app.
        # See learning/data_quality.py.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import overdue_training_handler

        register(DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE, overdue_training_handler)

        # HCM remediation H-3: this app's personal-data domain in
        # rbac_audit's subject-export registry.
        from rbac_audit.subject_export import register as register_export_handler

        from .subject_export import export_handler

        register_export_handler("learning.TrainingRecord", export_handler)
