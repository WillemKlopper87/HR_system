"""Probation workflow (Code on integrating EE into HR practice, probation
section): opened by hr_admin, reviewed by the line manager, decided by
hr_admin, plus the completion-rate dashboard. Split out of views.py
(HR_Code_report.md M5) -- no behavior change, just a workflow-boundary
move; see that module's own docstring for the app's overall split."""
from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.aggregates import percentage, suppress_related_counts
from rbac_audit.audit import log_access
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rbac_audit.models import AuditLogEntry
from rbac_audit.permissions import can_see_unsuppressed_aggregates, has_role, has_row_access
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import ProbationPeriod, ProbationReview
from .permissions import IsHRAdmin
from .serializers import ProbationPeriodSerializer, ProbationReviewSerializer


class ProbationPeriodViewSet(viewsets.ModelViewSet):
    """Code on integrating EE into HR practice, probation section — a
    probation window opened by hr_admin, reviewed by the line manager
    (ProbationReviewViewSet below), decided by hr_admin. Same
    RowScopePermission row-scoping learning's per-employee records use:
    the employee sees their own, their manager sees their reports', hr_admin
    sees all."""

    queryset = ProbationPeriod.objects.select_related("employee", "outcome_by").prefetch_related("reviews")
    serializer_class = ProbationPeriodSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        if not has_role(actor, "hr_admin"):
            raise ValidationError("Only hr_admin can open a probation period.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def record_outcome(self, request, pk=None):
        """hr_admin only. No workflow gate beyond "still open" — a
        CONFIRMED/TERMINATED period is closed; EXTENDED can still receive
        a later, final outcome."""
        period = self.get_object()
        actor = get_request_employee(request)
        if not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can record a probation outcome."}, status=403)
        if period.status not in (ProbationPeriod.Status.IN_PROGRESS, ProbationPeriod.Status.EXTENDED):
            return Response({"detail": f"Probation is already {period.get_status_display()}."}, status=400)
        new_status = request.data.get("status")
        valid_statuses = {
            ProbationPeriod.Status.CONFIRMED, ProbationPeriod.Status.EXTENDED, ProbationPeriod.Status.TERMINATED,
        }
        if new_status not in valid_statuses:
            return Response({"detail": "status must be one of confirmed, extended, terminated."}, status=400)
        update_fields = ["status", "outcome_at", "outcome_by", "outcome_notes"]
        period.status = new_status
        period.outcome_at = timezone.now()
        period.outcome_by = actor
        period.outcome_notes = request.data.get("notes", "")
        if new_status == ProbationPeriod.Status.EXTENDED:
            raw_end_date = request.data.get("end_date")
            new_end_date = parse_date(raw_end_date) if raw_end_date else None
            if new_end_date is None:
                return Response({"detail": "A valid end_date is required when extending probation."}, status=400)
            if new_end_date <= period.end_date:
                return Response(
                    {"detail": f"The new end_date must be after the current end date ({period.end_date})."},
                    status=400,
                )
            period.end_date = new_end_date
            update_fields.append("end_date")
        period.save(update_fields=update_fields)
        return Response(self.get_serializer(period).data)


class ProbationReviewViewSet(viewsets.ModelViewSet):
    queryset = ProbationReview.objects.select_related("probation_period__employee", "reviewed_by")
    serializer_class = ProbationReviewSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        period_id = int_query_param(self.request, "probation_period")
        if period_id is not None:
            queryset = queryset.filter(probation_period_id=period_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee, employee_field="probation_period__employee")

    def get_target_employee(self, obj):
        return obj.probation_period.employee

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        if not (has_role(actor, "hr_admin") or has_role(actor, "line_manager")):
            raise ValidationError("Only hr_admin or a line manager can record a probation review.")
        period = serializer.validated_data["probation_period"]
        if not has_row_access(actor, period.employee):
            raise PermissionDenied("You can only review probation for an employee in your reporting scope.")
        serializer.save(reviewed_by=actor)

    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        """Employee-only countersignature bound to the exact review payload."""
        requested_review = self.get_object()
        actor = get_request_employee(request)
        if actor is None or actor.pk != requested_review.probation_period.employee_id:
            return Response({"detail": "Only the employee can countersign this probation review."}, status=403)
        password = request.data.get("password")
        if not password or not request.user.check_password(password):
            return Response({"detail": "Your current password is required to countersign the review."}, status=400)

        with transaction.atomic():
            review = ProbationReview.objects.select_for_update().select_related(
                "probation_period__employee", "reviewed_by"
            ).get(pk=requested_review.pk)
            if review.employee_signed_at is not None:
                return Response({"detail": "This review has already been countersigned."}, status=409)
            payload = {
                "id": review.pk,
                "probation_period": review.probation_period_id,
                "review_date": review.review_date.isoformat(),
                "reviewed_by": review.reviewed_by_id,
                "recommendation": review.recommendation,
                "comments": review.comments,
            }
            review.employee_signature_sha256 = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            review.employee_signed_at = timezone.now()
            review.save(update_fields=["employee_signed_at", "employee_signature_sha256"])
            log_access(
                actor=actor, action=AuditLogEntry.Action.UPDATE,
                entity_type="core_hr.ProbationReview", entity_id=review.pk,
                field_tier=FieldTier.INTERNAL,
                fields_touched=f"employee countersignature sha256={review.employee_signature_sha256[:12]}…",
            )
        return Response(self.get_serializer(review).data)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, IsHRAdmin])
def probation_completion_dashboard(request):
    """Code on integrating EE into HR practice, probation section:
    "completion rates by designated group". Only CLOSED periods
    (confirmed or terminated) count towards a rate -- one still
    IN_PROGRESS/EXTENDED hasn't reached an outcome yet, so including it
    would understate confirmation until every open case resolves.
    hr_admin only, same reasoning training_compliance_dashboard uses:
    this is a management rollup naming individuals' outcomes, not a
    self-service view."""
    can_see_unsuppressed = can_see_unsuppressed_aggregates(get_request_employee(request), FieldTier.SENSITIVE)
    closed = ProbationPeriod.objects.filter(
        status__in=[ProbationPeriod.Status.CONFIRMED, ProbationPeriod.Status.TERMINATED]
    ).select_related("employee")
    # As-at the outcome date, not today -- a later transfer or demographic
    # correction must not silently rewrite an already-closed compliance
    # result (regulatory review P1: historical employee versions).
    versions = {
        period.pk: period.employee.version_as_at(period.outcome_at.date())
        for period in closed if period.outcome_at is not None
    }

    def _breakdown(group_field: str):
        buckets: dict[str, dict[str, int]] = {}
        for period in closed:
            version = versions.get(period.pk)
            key = getattr(version, group_field, None) if version else None
            if key is None:
                continue
            bucket = buckets.setdefault(key, {"confirmed": 0, "terminated": 0})
            bucket["confirmed" if period.status == ProbationPeriod.Status.CONFIRMED else "terminated"] += 1
        result = []
        for key, counts in sorted(buckets.items()):
            total = counts["confirmed"] + counts["terminated"]
            displayed, complementary = suppress_related_counts(
                counts, suppress=not can_see_unsuppressed
            )
            result.append({
                "key": key,
                "confirmed": displayed["confirmed"],
                "terminated": displayed["terminated"],
                "completion_pct": percentage(
                    counts["confirmed"], total, numerator_suppressed=complementary
                ),
                "suppressed": complementary,
            })
        return result

    total_closed = closed.count()
    total_confirmed = closed.filter(status=ProbationPeriod.Status.CONFIRMED).count()
    return Response({
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "total_closed": total_closed,
        "total_confirmed": total_confirmed,
        "overall_completion_pct": round(total_confirmed / total_closed * 100, 1) if total_closed else None,
        "in_progress": ProbationPeriod.objects.filter(
            status__in=[ProbationPeriod.Status.IN_PROGRESS, ProbationPeriod.Status.EXTENDED]
        ).count(),
        "by_race": _breakdown("race"),
        "by_gender": _breakdown("gender"),
        "by_disability_status": _breakdown("disability_status"),
    })
