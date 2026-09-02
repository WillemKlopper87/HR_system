"""The system-detected data-quality exception queue. Split out of
views.py (HR_Code_report.md M5) -- no behavior change; see that
module's own docstring for the app's overall split."""
from __future__ import annotations

from django.utils import timezone
from rbac_audit.audit import log_access
from rbac_audit.drf import get_request_employee
from rbac_audit.models import AuditLogEntry
from rbac_audit.tiers import FieldTier
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .data_quality import run_data_quality_checks
from .models import DataQualityException
from .permissions import IsHRAdmin
from .serializers import DataQualityExceptionSerializer


class DataQualityExceptionViewSet(viewsets.ReadOnlyModelViewSet):
    """RBAC-Roles.md: the data-quality queue is hr_admin's. Exceptions are
    system-detected (data_quality.run_data_quality_checks), not
    user-created, hence read-only plus two explicit actions rather than a
    full ModelViewSet."""

    serializer_class = DataQualityExceptionSerializer
    permission_classes = [IsHRAdmin]

    def get_queryset(self):
        queryset = DataQualityException.objects.select_related("employee")
        if self.action == "list" and self.request.query_params.get("resolved") != "true":
            # Detail lookups (retrieve/resolve) must see resolved rows too
            # — otherwise resolving an already-resolved exception 404s
            # instead of returning the "already resolved" 400 below.
            queryset = queryset.filter(resolved_at__isnull=True)
        return queryset

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Manual dismissal (e.g. an accepted/explained exception). If the
        underlying condition is still present, the next run_checks call
        re-opens a fresh exception row — resolving here doesn't suppress
        detection, it just closes this occurrence."""
        exception = self.get_object()
        if exception.resolved_at is not None:
            return Response({"detail": "Already resolved."}, status=400)
        exception.resolved_at = timezone.now()
        exception.save(update_fields=["resolved_at"])
        log_access(
            actor=get_request_employee(request),
            action=AuditLogEntry.Action.UPDATE,
            entity_type="core_hr.DataQualityException",
            entity_id=exception.pk,
            field_tier=FieldTier.PUBLIC,
            fields_touched="resolved_at",
        )
        return Response(self.get_serializer(exception).data)

    @action(detail=False, methods=["post"])
    def run_checks(self, request):
        """Triggers data_quality.run_data_quality_checks() on demand.
        Nothing schedules this automatically yet (no Celery beat job) —
        that's flagged in Sprint-0-Decision-Log.md as post-Sprint-16
        hardening work, not a Sprint 3 omission."""
        result = run_data_quality_checks()
        return Response(result)
