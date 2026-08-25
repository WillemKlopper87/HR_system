from django.apps import AppConfig


class PerformanceConfig(AppConfig):
    name = 'performance'

    def ready(self):
        # Data-quality handler for this app's own overdue-stage check
        # (H3 org-wide sweep) -- registered with the shared executor in
        # core_hr, which never imports a peer app. See performance/data_quality.py.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import missing_calibration_handler, overdue_agreement_handler

        register(DataQualityException.ExceptionType.PERFORMANCE_OVERDUE, overdue_agreement_handler)
        register(DataQualityException.ExceptionType.PERFORMANCE_NO_CALIBRATION, missing_calibration_handler)
