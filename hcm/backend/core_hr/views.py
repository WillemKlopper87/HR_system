"""Employee identity records (Employee / EmployeeVersion) -- the app's
namesake aggregate. Every other workflow this app used to also carry
here now lives in its own views_<workflow>.py module (probation, exit
interviews, employment changes, reference data, dependants, data
quality, dashboards), split out per HR_Code_report.md M5's "separate
viewsets by aggregate/workflow" recommendation. core_hr/urls.py wires
all of them together; nothing outside this app imports from here or
those siblings directly (only urls.py files import view modules by
convention throughout this codebase), so the split needed no consumer
changes beyond that one file."""
from __future__ import annotations

from types import SimpleNamespace

from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema
from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent, record_consent
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.permissions import has_role, is_in_reporting_chain
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action
from .models import Employee, EmployeeVersion
from .serializers import (
    ContractActionInputSerializer,
    ContractRenewalDecisionSerializer,
    EmployeeSearchSummarySerializer,
    EmployeeSerializer,
    EmployeeVersionSerializer,
    OrgChartNodeSerializer,
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
                position_id=payload.validated_data.get("position_id"),
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

        employment_status = self.request.query_params.get("employment_status")
        if employment_status:
            queryset = queryset.filter(
                versions__in=EmployeeVersion.objects.current().filter(employment_status=employment_status)
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

    @extend_schema(responses=OrgChartNodeSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="org-chart")
    def org_chart(self, request):
        """Return only the current reporting topology visible to the actor."""
        queryset = row_scoped_queryset(
            EmployeeVersion.objects.current().select_related("employee", "department", "manager"),
            get_request_employee(request),
        ).order_by("-created_at", "-pk")
        page = self.paginate_queryset(queryset)
        serializer = OrgChartNodeSerializer(page, many=True)
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
