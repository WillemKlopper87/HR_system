"""Exit interview record-keeping and its reason-breakdown dashboard. Split
out of views.py (HR_Code_report.md M5) -- no behavior change. Named
`views_exit_interviews`, not `views_exits`, to stay distinct from the
employment-exit STATE MACHINE (exits.py / EmploymentChangeViewSet in
views_employment_changes.py) -- this module only records what someone
said in an exit interview, after that state machine has already run."""
from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.aggregates import suppress_count, suppress_related_counts
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.permissions import can_see_unsuppressed_aggregates
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ExitInterview
from .permissions import IsHRAdmin
from .serializers import ExitInterviewSerializer


class ExitInterviewViewSet(viewsets.ModelViewSet):
    """hr_admin only -- same posture as training_compliance_dashboard:
    a management record naming individuals' departure reasons, not a
    self-service or line-manager view. Reusable across two triggers
    (a genuine exit via employment_change, or a probation
    non-confirmation via probation_period), per the Code on integrating
    EE into HR practice's own cross-reference between the two."""

    queryset = ExitInterview.objects.select_related("employee", "conducted_by")
    serializer_class = ExitInterviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsHRAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(conducted_by=get_request_employee(self.request))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, IsHRAdmin])
def exit_interview_dashboard(request):
    """Code on integrating EE into HR practice, termination/retention
    section: exit reasons reviewed by designated group. Reuses the
    current EmployeeVersion for each interviewed employee -- same
    approach probation_completion_dashboard takes, and the same caveat:
    an employee whose demographics are NOT_DISCLOSED on both race and
    gender is invisible to the by_race/by_gender breakdowns (nothing to
    group them under), same as every other workforce breakdown in this
    app."""
    can_see_unsuppressed = can_see_unsuppressed_aggregates(get_request_employee(request), FieldTier.SENSITIVE)
    interviews = ExitInterview.objects.select_related("employee")
    # As-at the interview date, not today -- same historical-accuracy
    # reasoning as probation_completion_dashboard above.
    versions = {
        interview.pk: interview.employee.version_as_at(interview.interview_date)
        for interview in interviews
    }

    def _breakdown(group_field: str):
        buckets: dict[str, dict[str, int]] = {}
        for interview in interviews:
            version = versions.get(interview.pk)
            key = getattr(version, group_field, None) if version else None
            if key is None:
                continue
            bucket = buckets.setdefault(key, {})
            bucket[interview.primary_reason] = bucket.get(interview.primary_reason, 0) + 1
        result = []
        for key, reasons in sorted(buckets.items()):
            total = sum(reasons.values())
            displayed, complementary = suppress_related_counts(
                reasons, suppress=not can_see_unsuppressed
            )
            result.append({
                "key": key,
                "total": suppress_count(total, suppress=not can_see_unsuppressed),
                "by_reason": displayed,
                "suppressed": complementary,
            })
        return result

    reason_counts: dict[str, int] = {}
    for interview in interviews:
        reason_counts[interview.primary_reason] = reason_counts.get(interview.primary_reason, 0) + 1

    return Response({
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "total_interviews": interviews.count(),
        "by_reason": [{"key": key, "count": count} for key, count in sorted(reason_counts.items())],
        "by_race": _breakdown("race"),
        "by_gender": _breakdown("gender"),
        "by_disability_status": _breakdown("disability_status"),
    })
