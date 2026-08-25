"""Data-quality handler for critical posts with no ready-now/ready-soon
successor (spec §2.9). Registered from `succession.apps.SuccessionConfig.
ready()`; executed by `core_hr.data_quality.run_data_quality_checks`."""
from __future__ import annotations

from .models import CriticalPost, SuccessionCandidate


def critical_post_no_successor_handler():
    for post in CriticalPost.objects.filter(active=True).select_related("position"):
        occupant_version = post.position.current_occupant
        if occupant_version is None:
            # Vacant critical post -- no employee to attach the exception
            # to, and the vacancy itself is already visible on /positions
            # to everyone who can see the post at all (spec §2.9).
            continue
        has_ready_successor = post.candidates.filter(
            active=True, readiness__in=SuccessionCandidate.READY_SOON
        ).exists()
        if not has_ready_successor:
            yield (
                occupant_version.employee,
                f"Critical post {post.position.post_number} ({post.position.title}) has no ready-now or "
                "ready-soon successor.",
            )
