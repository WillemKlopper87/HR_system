from __future__ import annotations

from types import SimpleNamespace

from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent, record_consent
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.permissions import can_see_unsuppressed_aggregates, has_role
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action
from .data_quality import run_data_quality_checks
from .models import (
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
    JobGrade,
    Location,
    OccupationalLevel,
)
from .permissions import IsHRAdmin, IsHRAdminOrReadOnly
from .serializers import (
    ContractActionInputSerializer,
    ContractRenewalDecisionSerializer,
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
        employee_id = int_query_param(self.request, "employee")
        if employee_id is not None:
            queryset = queryset.filter(employee_id=employee_id)
        if self.request.query_params.get("current") == "true":
            queryset = queryset.current()
        if self.request.query_params.get("fixed_term") == "true":
            queryset = queryset.filter(
                employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
                contract_end_date__isnull=False,
            )

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

    @action(detail=True, methods=["post"])
    def recommend_contract(self, request, pk=None):
        """Line manager only (RBAC-Roles.md; C1 part 2 design spec §3.2).
        get_object() above already ran RowScopePermission.has_object_permission
        -- an hr_admin/auditor (row_scope=ALL) or the target's own manager
        (row_scope=own_team, via the reporting chain) reaches this body;
        anyone else already got a RowScopePermission-driven 403. has_role()
        narrows further: row access alone doesn't mean "is this specific
        person's manager" -- an auditor has row access too but must never
        recommend."""
        version = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not has_role(actor, "line_manager"):
            return Response({"detail": "Only the line manager can recommend a contract action."}, status=403)
        payload = ContractActionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            decision = recommend_contract_action(
                version, actor=actor, action=payload.validated_data["action"],
                comment=payload.validated_data["comment"], end_date=payload.validated_data.get("end_date"),
            )
        except ContractDecisionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(ContractRenewalDecisionSerializer(decision).data)

    @action(detail=True, methods=["post"])
    def decide_contract(self, request, pk=None):
        """hr_admin only -- same layering as recommend_contract above."""
        version = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can decide a contract action."}, status=403)
        payload = ContractActionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            decision = decide_contract_action(
                version, actor=actor, action=payload.validated_data["action"],
                comment=payload.validated_data["comment"], end_date=payload.validated_data.get("end_date"),
            )
        except ContractDecisionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(ContractRenewalDecisionSerializer(decision).data)


class EmployeeViewSet(viewsets.ModelViewSet):
    """Identity records (core_hr.Employee) — same row-scope + field-tier +
    audit pattern as EmployeeVersionViewSet. The list/detail UI (Sprint 3)
    joins this with EmployeeVersionViewSet's ?current=true for a
    complete "who they are + where they sit today" view.

    Writable since Sprint 15 (ESS) — PATCH plus the two POST actions below
    only; no generic create/delete (employees are created via hire()/
    recruitment, never through this endpoint — create() is overridden
    below rather than dropped from http_method_names, since DRF's router
    wires POST-method actions like consent/self_identify through the same
    method-name allowlist as the generic create()). RowScopePermission's
    object-level check would let any row-access-holder (e.g. line_manager
    over a report, auditor via an all-scope role) reach PATCH here, which
    is too broad for a write — EmployeeSerializer.validate() is the real
    write gate (self or hr_admin only, ESS-editable fields only)."""

    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def create(self, request, *args, **kwargs):
        return Response({"detail": 'Method "POST" not allowed.'}, status=405)

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

    @action(detail=True, methods=["post"])
    def consent(self, request, pk=None):
        """Same shape as recruitment.ApplicantViewSet.consent, generalized
        the same way — purpose defaults to demographic_self_id (this
        action's primary ESS use: gating self_identify below)."""
        employee = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not (actor.id == employee.id or has_role(actor, "hr_admin")):
            return Response({"detail": "You don't have access to record consent for this employee."}, status=403)
        purpose = request.data.get("purpose", ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID)
        if purpose not in ConsentRecord.Purpose.values:
            return Response({"detail": "Invalid purpose."}, status=400)
        record_consent(
            employee=employee,
            purpose=purpose,
            lawful_basis=request.data.get("lawful_basis", ConsentRecord.LawfulBasis.CONSENT),
            text_version=request.data.get("text_version", "v1"),
            actor=actor,
        )
        return Response({"detail": "Consent recorded."}, status=201)

    @action(detail=True, methods=["post"])
    def self_identify(self, request, pk=None):
        """Employee (or hr_admin, on their behalf) submits/updates
        race/gender/disability self-identification — consent-gated the
        same way recruitment.ApplicantSerializer gates applicant
        demographic writes. Updates the CURRENT EmployeeVersion's fields
        in place rather than going through apply_lifecycle_event: this is
        a classification correction, not an employment-lifecycle fact, so
        none of the fixed EmploymentEvent.EventType choices fit, and
        EmployeeVersion's own HistoricalRecords already gives it an audit
        trail without needing a new version+event."""
        employee = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not (actor.id == employee.id or has_role(actor, "hr_admin")):
            return Response({"detail": "You don't have access to self-identify for this employee."}, status=403)
        if not has_active_consent(employee=employee, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID):
            return Response(
                {"detail": "Active consent is required first — POST /employees/{id}/consent/."}, status=400
            )

        choice_fields = {
            "race": EmployeeVersion.Race.values,
            "gender": EmployeeVersion.Gender.values,
            "disability_status": EmployeeVersion.DisabilityStatus.values,
        }
        allowed_fields = set(choice_fields) | {"disability_detail"}
        fields = {k: v for k, v in request.data.items() if k in allowed_fields}
        if not fields:
            return Response({"detail": "No self-ID fields provided."}, status=400)
        for field, value in fields.items():
            if field in choice_fields and value not in choice_fields[field]:
                return Response({"detail": f"Invalid value for {field}."}, status=400)

        version = employee.current_version
        if version is None:
            return Response({"detail": "Employee has no current version to update."}, status=400)

        update_fields = []
        for field, value in fields.items():
            setattr(version, field, value)
            update_fields.append(field)
        if "race" in fields:
            version.race_source = EmployeeVersion.DemographicSource.SELF_IDENTIFIED
            update_fields.append("race_source")
        if {"disability_status", "disability_detail"} & fields.keys():
            version.disability_source = EmployeeVersion.DemographicSource.SELF_IDENTIFIED
            update_fields.append("disability_source")
        version.save(update_fields=update_fields)

        log_access(
            actor=actor,
            action=AuditLogEntry.Action.UPDATE,
            entity_type="core_hr.EmployeeVersion",
            entity_id=version.pk,
            field_tier=FieldTier.SENSITIVE,
            fields_touched=",".join(fields.keys()),
        )
        # Not self.get_serializer_context(): that context's `view` is this
        # EmployeeViewSet, whose get_target_employee(obj) assumes obj is an
        # Employee (returns obj itself) — wrong for a TieredModelSerializer
        # rendering an EmployeeVersion, which needs obj.employee instead
        # (EmployeeVersionViewSet's own get_target_employee shape).
        version_context = {"request": request, "view": SimpleNamespace(get_target_employee=lambda obj: obj.employee)}
        return Response(EmployeeVersionSerializer(version, context=version_context).data)


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


@extend_schema(responses=OpenApiTypes.OBJECT)
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
