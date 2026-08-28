from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.aggregates import SMALL_CELL_THRESHOLD, percentage, suppress_count, suppress_related_counts
from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent, record_consent
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.permissions import can_see_unsuppressed_aggregates, has_role, has_row_access, is_in_reporting_chain
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action
from .data_quality import run_data_quality_checks
from .exits import EmploymentChangeError, cancel_employment_change, confirm_employment_change, propose_employment_change
from .models import (
    DataQualityException,
    Dependant,
    Department,
    Employee,
    EmergencyContact,
    EmployeeVersion,
    EmploymentChange,
    JobGrade,
    Location,
    ExitInterview,
    OccupationalLevel,
    ProbationPeriod,
    ProbationReview,
)
from .permissions import EmploymentChangePermission, IsHRAdmin, IsHRAdminOrReadOnly, IsSelfOrHRAdmin
from .serializers import (
    ContractActionInputSerializer,
    ContractRenewalDecisionSerializer,
    DataQualityExceptionSerializer,
    DependantSerializer,
    DepartmentSerializer,
    EmergencyContactSerializer,
    EmployeeSearchSummarySerializer,
    EmployeeSerializer,
    EmployeeVersionSerializer,
    EmploymentChangeSerializer,
    JobGradeSerializer,
    LocationSerializer,
    OccupationalLevelSerializer,
    ExitInterviewSerializer,
    ProbationPeriodSerializer,
    ProbationReviewSerializer,
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
        """Line manager of THIS employee only (RBAC-Roles.md; C1 part 2
        design spec §6). get_object() above already ran
        RowScopePermission.has_object_permission -- an hr_admin/auditor
        (row_scope=ALL) or the target's own manager (row_scope=own_team,
        via the reporting chain) reaches this body; anyone else already
        got a RowScopePermission-driven 403.

        The narrowing is deliberately `has_role(...) AND
        is_in_reporting_chain(...)`, not has_role() alone: has_role() is
        scope-blind, and RowScopePermission grants object access if ANY
        active role covers the target, so an actor holding line_manager
        *plus* any row_scope=all role could otherwise recommend for every
        employee in the organisation. Not hypothetical -- RBAC-Roles.md
        derives line_manager from having direct reports, so in production
        an hr_head/ee_manager with reports holds both. This is the same
        cross-role composition hazard
        rbac_audit.permissions.can_access_tier_for_target exists to close,
        and the same idiom serializers.py already uses for this feature's
        subject-visibility gate.

        is_in_reporting_chain is transitive (skip-level) rather than
        direct-manager-only; that is the codebase-wide convention for "own
        team" (it backs row_scope=own_team itself), and the spec's §6
        wording was amended from "direct reports only" to "reporting
        chain" to match. The frontend keeps a stricter direct-manager
        check on the Recommend button -- a deliberate asymmetry noted
        there."""
        version = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not (has_role(actor, "line_manager") and is_in_reporting_chain(actor, version.employee)):
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
        queryset = Employee.objects.prefetch_related(
            Prefetch(
                "versions",
                queryset=EmployeeVersion.objects.current().only(
                    "employee_id", "department_id", "occupational_level_id", "employment_status"
                ),
                to_attr="current_versions_for_summary",
            )
        )
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

    @extend_schema(responses=EmployeeSearchSummarySerializer(many=True))
    @action(detail=False, methods=["get"], url_path="search-summary")
    def search_summary(self, request):
        """Return only the identity fields needed by employee selectors.

        The explicit row-scope call is important: collection actions do not
        pass through the list-only scoping branch in ``get_queryset``.
        """
        query = request.query_params.get("q", "").strip()
        queryset = row_scoped_queryset(
            Employee.objects.all(),
            get_request_employee(request),
            employee_field=None,
        )
        if len(query) < 2:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(preferred_name__icontains=query)
                | Q(employee_number__icontains=query)
            )
        page = self.paginate_queryset(queryset.order_by("-created_at", "-pk"))
        serializer = EmployeeSearchSummarySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

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


class EmploymentChangeViewSet(viewsets.ModelViewSet):
    """The exit state machine's HTTP surface (C1 part 3, design spec
    docs/superpowers/specs/2026-08-20-employment-exit-states-design.md).
    exits.py's service layer already enforces every state rule; this
    viewset's job is EmploymentChangePermission's role gate (spec §8) and
    translating EmploymentChangeError -> 400, never re-implementing
    domain logic (exits.py's own module docstring on the 403-vs-400
    split, and contracts.py's decide_contract_action for the worked
    example of NOT letting a bare `except ValueError` swallow it).

    No PATCH/PUT/DELETE — a change only ever moves forward through
    propose -> confirm(/cancel) -> execute (execute itself has no
    endpoint: it happens inside confirm when due, or via the daily beat
    job otherwise), the same shape as CompProposalViewSet/PositionViewSet."""

    queryset = EmploymentChange.objects.select_related(
        "employee", "proposed_by", "confirmed_by", "cancelled_by", "lifts_suspension", "resulting_event"
    )
    serializer_class = EmploymentChangeSerializer
    permission_classes = [EmploymentChangePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        employee_id = int_query_param(self.request, "employee")
        if employee_id is not None:
            queryset = queryset.filter(employee_id=employee_id)
        return queryset.order_by("-proposed_at")

    def perform_create(self, serializer):
        try:
            serializer.instance = propose_employment_change(
                employee=serializer.validated_data["employee"],
                actor=get_request_employee(self.request),
                change_type=serializer.validated_data["change_type"],
                effective_date=serializer.validated_data["effective_date"],
                reason=serializer.validated_data["reason"],
            )
        except EmploymentChangeError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """hr_admin only (EmploymentChangePermission); the tiered-type
        "must be a different person" rule (spec §4.2) is decided from
        identity alone, not role, so it stays in exits.py and surfaces
        here as the 400 branch, not a second 403 check."""
        change = self.get_object()
        actor = get_request_employee(request)
        try:
            confirm_employment_change(change, actor=actor)
        except EmploymentChangeError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(change).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Any hr_admin, not just the proposer (spec §8)."""
        change = self.get_object()
        actor = get_request_employee(request)
        try:
            cancel_employment_change(change, actor=actor, reason=request.data.get("reason", ""))
        except EmploymentChangeError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(change).data)


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


class _SelfOrHRAdminEmployeeScopedViewSet(viewsets.ModelViewSet):
    """Shared shape for DependantViewSet/EmergencyContactViewSet (C2 design
    spec §2.8, §5.2): self-or-hr_admin only, narrower than
    RowScopePermission's row-scope (a line_manager never manages a
    report's dependants/emergency contacts). List is filtered to the
    caller's own rows unless they hold hr_admin; detail lookups are left
    unfiltered so a non-owner gets a 403 via IsSelfOrHRAdmin rather than a
    queryset-driven 404 -- same shape as
    policies.PolicyAcknowledgmentViewSet.get_queryset (no secrecy reason
    to hide existence here, unlike Policy's draft-hiding)."""

    model = None  # set by subclasses
    permission_classes = [IsSelfOrHRAdmin]

    def get_queryset(self):
        queryset = self.model.objects.select_related("employee")
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        if employee is not None and has_role(employee, "hr_admin"):
            return queryset
        return queryset.filter(employee=employee)

    def get_target_employee(self, obj):
        return obj.employee


class DependantViewSet(_SelfOrHRAdminEmployeeScopedViewSet):
    model = Dependant
    serializer_class = DependantSerializer


class EmergencyContactViewSet(_SelfOrHRAdminEmployeeScopedViewSet):
    model = EmergencyContact
    serializer_class = EmergencyContactSerializer


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
            is_small = suppress and 0 < count < SMALL_CELL_THRESHOLD
            result.append({
                "key": key,
                "count": suppress_count(count, suppress=suppress),
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
