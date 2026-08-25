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
