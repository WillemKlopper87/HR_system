from __future__ import annotations

from core_hr.models import Employee
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Policy, PolicyAcknowledgment
from .permissions import IsHRAdmin


@api_view(["GET"])
@permission_classes([IsHRAdmin])
def acknowledgment_dashboard(request):
    """Per currently-published policy: how much of the active workforce
    has acknowledged THIS version. Not small-cell-suppressed — unlike
    core_hr's headcount dashboard, acknowledgment status isn't a
    Sensitive-tier demographic breakdown (Data-Dictionary.md doesn't tier
    it), same "Internal-tier, no suppression" reasoning as
    learning.skills_inventory."""
    today = timezone.localdate()
    total_active = sum(1 for e in Employee.objects.all() if e.current_version is not None)

    rows = []
    for policy in Policy.objects.filter(status=Policy.Status.PUBLISHED).order_by("title"):
        acknowledged_count = PolicyAcknowledgment.objects.filter(policy=policy).count()
        rows.append({
            "policy_id": policy.id,
            "title": policy.title,
            "category": policy.category,
            "version": policy.version,
            "published_at": policy.published_at,
            "total_employees": total_active,
            "acknowledged_count": acknowledged_count,
            "acknowledged_pct": round(acknowledged_count / total_active * 100, 1) if total_active else 0.0,
        })

    return Response({"as_of": today, "policies": rows})
