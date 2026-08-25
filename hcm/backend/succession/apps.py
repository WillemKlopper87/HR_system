from django.apps import AppConfig


class SuccessionConfig(AppConfig):
    """Succession planning / talent pools (C6, second sub-item). Spec:
    docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md

    New app, not folded into establishment (SHARED_KERNEL -- would over-
    expose politically sensitive nominee data to every importer) or
    learning (wrong domain fit -- see spec §2.1). Reads establishment.
    Position and core_hr.Employee directly (both kernel); reads learning/
    performance only through their queries.py seams (§2.7)."""

    name = "succession"

    def ready(self):
        # Data-quality handler for "critical post with no ready-now/
        # ready-soon successor" (spec §2.9) -- registered with the shared
        # executor in core_hr, which never imports a peer app.
        from core_hr.data_quality import register
        from core_hr.models import DataQualityException

        from .data_quality import critical_post_no_successor_handler

        register(DataQualityException.ExceptionType.CRITICAL_POST_NO_SUCCESSOR, critical_post_no_successor_handler)
