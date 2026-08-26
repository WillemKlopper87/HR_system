from django.apps import AppConfig


class EeReportingConfig(AppConfig):
    name = 'ee_reporting'
    verbose_name = 'EE Reporting'

    def ready(self):
        # H3 org-wide data-quality sweep — same registration shape as
        # compensation/learning/succession. See ee_reporting/data_quality.py.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import measure_overdue_handler

        register(DataQualityException.ExceptionType.EE_MEASURE_OVERDUE, measure_overdue_handler)
