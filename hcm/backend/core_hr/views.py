from __future__ import annotations

from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rbac_audit.audit import log_access
from rbac_audit.drf import RowScopePermission, get_request_employee, row_scoped_queryset
from rbac_audit.models import AuditLogEntry
from rbac_audit.permissions import can_see_unsuppressed_aggregates
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .data_quality import run_data_quality_checks
from .models import DataQualityException, Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from .permissions import IsHRAdmin, IsHRAdminOrReadOnly
from .serializers import (
    DataQualityExceptionSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    EmployeeVersionSerializer,
    JobGradeSerializer,
    LocationSerializer,
    OccupationalLevelSerializer,
)


class EmployeeVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """Row-scope + field-tier filtering + audit logging, proven end-to-end
    in Sprint 2. Sprint 3 adds two read-only query params for the
    dashboards: ?employee=<id> (that employee's full version history, for
    the detail page) and ?current=true (only versions valid today, for
    list/aggregate views)."""

    serializer_class = EmployeeVersionSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = EmployeeVersion.objects.select_related(
            "employee", "department", "occupational_level", "job_grade", "manager", "location"
        )
        employee_id = self.request.query_params.get("employee")
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if self.request.query_params.get("current") == "true":
            queryset = queryset.current()

        if self.action != "list":
            # Detail lookups must NOT be row-scope-filtered here: DRF's
            # get_object() raises 404 for anything missing from the
            # queryset before has_object_permission ever runs, which
            # would silently skip RowScopePermission's audit logging.
            # RowScopePermission enforces (and logs) the block instead,
            # yielding 403. List filtering below is still queryset-level
            # for efficiency, since there's no single object to gate.
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee


class EmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    """Identity records (core_hr.Employee) — same row-scope + field-tier +
    audit pattern as EmployeeVersionViewSet. The list/detail UI (Sprint 3)
    joins this with EmployeeVersionViewSet's ?current=true for a
    complete "who they are + where they sit today" view."""

    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = Employee.objects.all()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_number__icontains=search)
                | Q(work_email__icontains=search)
            )

        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee, employee_field=None)

    def get_target_employee(self, obj):
        return obj


class ProtectedDeleteMixin:
    """Reference tables (Department/JobGrade/Location) are PROTECTed
    against deletion while in use (employee_versions FK). Surface that as
    a 400 with a clear message instead of DRF's default 500."""

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "This record is still referenced by employee records and cannot be deleted. "
                "Mark it inactive instead."
            )


class DepartmentViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class OccupationalLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """The six statutory EEA occupational levels are fixed by law and
    seeded via migration — not user-manageable, hence read-only."""

    queryset = OccupationalLevel.objects.all()
    serializer_class = OccupationalLevelSerializer
    permission_classes = [permissions.IsAuthenticated]


class JobGradeViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = JobGrade.objects.select_related("occupational_level").all()
    serializer_class = JobGradeSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class LocationViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsHRAdminOrReadOnly]


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


SMALL_CELL_THRESHOLD = 5


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def headcount_dashboard(request):
    """Sprint 3's basic org-wide headcount dashboard. Breakdowns reuse the
    same field-tier grants as everywhere else: a role without Sensitive-tier
    read gets small-cell-suppressed counts on demographic breakdowns
    (RBAC-Roles.md standing rule 1 / gap C6), not the full RBAC field
    machinery, since these are aggregates rather than individual records."""
    employee = get_request_employee(request)
    can_see_unsuppressed = can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)

    current_versions = EmployeeVersion.objects.current().select_related(
        "department", "occupational_level", "job_grade"
    )

    def _breakdown(group_field: str, *, suppress: bool):
        rows = current_versions.values(group_field).annotate(count=Count("id")).order_by(group_field)
        result = []
        for row in rows:
            key = row[group_field]
            if key is None:
                continue
            count = row["count"]
            is_small = suppress and count < SMALL_CELL_THRESHOLD
            result.append({
                "key": key,
                "count": f"<{SMALL_CELL_THRESHOLD}" if is_small else count,
                "suppressed": is_small,
            })
        return result

    data = {
        "total_headcount": current_versions.count(),
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "by_department": _breakdown("department__name", suppress=False),
        "by_occupational_level": _breakdown("occupational_level__name", suppress=False),
        "by_job_grade": _breakdown("job_grade__name", suppress=False),
        "by_race": _breakdown("race", suppress=not can_see_unsuppressed),
        "by_gender": _breakdown("gender", suppress=not can_see_unsuppressed),
        "by_disability_status": _breakdown("disability_status", suppress=not can_see_unsuppressed),
    }
    return Response(data)
