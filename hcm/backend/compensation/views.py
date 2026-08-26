from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rbac_audit.stepup import RequiresPayrollStepUp
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ee_reporting.queries import latest_remuneration_for_employee
from performance.queries import latest_final_score

from .models import Benefit, BenefitsElection, CompCycle, CompProposal, PayBand
from .permissions import IsCompManagerOrHRAdmin, IsCompManagerOrHRAdminOrReadOnly, IsSelfOrCompManagerOrHRAdmin
from .serializers import (
    BenefitSerializer,
    BenefitsElectionSerializer,
    CompCycleSerializer,
    CompProposalSerializer,
    PayBandSerializer,
)
from .services import (
    ApprovalError,
    approve_proposal,
    close_cycle,
    open_cycle,
    propose_compensation_change,
    reject_proposal,
)


class PayBandViewSet(viewsets.ModelViewSet):
    """RequiresPayrollStepUp is layered on top of IsCompManagerOrHRAdmin,
    not instead of it — Data-Dictionary.md tiers pay_band "R" (Restricted),
    so holding the comp_manager/hr_admin role is necessary but no longer
    sufficient on its own; a live TOTP code + stated business
    justification (rbac_audit.stepup) is required too, time-boxed per
    STEPUP_GRANT_MINUTES."""

    queryset = PayBand.objects.select_related("job_grade", "created_by")
    serializer_class = PayBandSerializer
    permission_classes = [IsCompManagerOrHRAdmin, RequiresPayrollStepUp]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))


class CompCycleViewSet(viewsets.ModelViewSet):
    """A cycle row itself carries no individual's pay figure (name, dates,
    a budget total, a department, a status) — deliberately NOT
    RequiresPayrollStepUp, unlike PayBand/CompProposal (design spec §6):
    step-up exists for privileged access to someone else's Restricted-tier
    pay data, and a planning envelope isn't that."""

    queryset = CompCycle.objects.select_related("department", "created_by", "closed_by").prefetch_related(
        "proposals"
    )
    serializer_class = CompCycleSerializer
    permission_classes = [IsCompManagerOrHRAdmin]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        cycle = self.get_object()
        try:
            open_cycle(cycle)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(cycle).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        cycle = self.get_object()
        try:
            # close_cycle locks and re-fetches the row internally (it must,
            # to serialize against a concurrent create/approve — see
            # services.py), so it returns a NEW instance rather than
            # mutating this one in place; the response must serialize
            # that returned instance, not the pre-close object above.
            cycle = close_cycle(cycle, actor=get_request_employee(request))
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(cycle).data)


class CompProposalViewSet(viewsets.ModelViewSet):
    """No PATCH on core fields — a proposal is created once via 'propose'
    semantics (see perform_create) and thereafter only moves through the
    approve/reject actions, never edited in place. RequiresPayrollStepUp:
    see PayBandViewSet's docstring — comp_proposal is also "R"-tier.
    Supports ?cycle=<id> filtering for a cycle's own proposal list."""

    queryset = CompProposal.objects.select_related(
        "employee", "current_job_grade", "cycle", "proposed_by", "approved_by"
    )
    serializer_class = CompProposalSerializer
    permission_classes = [IsCompManagerOrHRAdmin, RequiresPayrollStepUp]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        cycle_id = self.request.query_params.get("cycle")
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.instance = propose_compensation_change(
                employee=serializer.validated_data["employee"],
                proposal_type=serializer.validated_data.get(
                    "proposal_type", CompProposal.ProposalType.INCREASE
                ),
                proposed_annual_salary=serializer.validated_data.get("proposed_annual_salary"),
                bonus_amount=serializer.validated_data.get("bonus_amount"),
                cycle=serializer.validated_data.get("cycle"),
                justification=serializer.validated_data.get("justification", ""),
                effective_date=serializer.validated_data.get("effective_date"),
                proposed_by=get_request_employee(self.request),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = self.get_object()
        try:
            approve_proposal(
                proposal,
                approver=get_request_employee(request),
                override_reason=request.data.get("override_reason", ""),
            )
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = self.get_object()
        try:
            reject_proposal(proposal, approver=get_request_employee(request))
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(proposal).data)


class BenefitViewSet(viewsets.ModelViewSet):
    """Read-open since Sprint 15 (ESS) — an employee needs to see what
    benefits exist to elect/waive them; only comp_manager/hr_admin manage
    the catalog itself."""

    queryset = Benefit.objects.all()
    serializer_class = BenefitSerializer
    permission_classes = [IsCompManagerOrHRAdminOrReadOnly]


class BenefitsElectionViewSet(viewsets.ModelViewSet):
    """Sprint 15 (ESS): an employee manages their own elections; comp_manager/
    hr_admin can still record/adjust anyone's, as before Sprint 15."""

    queryset = BenefitsElection.objects.select_related("employee", "benefit")
    serializer_class = BenefitsElectionSerializer
    permission_classes = [IsSelfOrCompManagerOrHRAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            # Detail lookups must NOT be row-scope-filtered here — same
            # reasoning as core_hr.EmployeeVersionViewSet.get_queryset():
            # DRF's get_object() 404s on anything missing from the queryset
            # before has_object_permission ever runs, which would silently
            # skip IsSelfOrCompManagerOrHRAdmin's block. Let that permission
            # produce the 403 instead. List filtering stays queryset-level.
            return queryset
        employee = get_request_employee(self.request)
        if employee is not None and (has_role(employee, "comp_manager") or has_role(employee, "hr_admin")):
            return queryset
        return queryset.filter(employee=employee)

    def perform_create(self, serializer):
        employee = get_request_employee(self.request)
        if employee is not None and (has_role(employee, "comp_manager") or has_role(employee, "hr_admin")):
            serializer.save()
        else:
            # Self-service: whatever `employee` the client sent is ignored —
            # you can only ever elect for yourself this way.
            serializer.save(employee=employee)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_total_rewards_statement(request):
    """A genuinely new, narrow self-scope carve-out (design spec §3) — the
    requester's OWN current salary (RemunerationRecord, the SAP-sourced
    actual, never CompProposal — spec §4), their OWN pay-band position
    (the one band for their OWN current job_grade, never any other
    grade's), their OWN benefits elections (already self-visible via
    MyBenefitsPage.tsx — folded in here for convenience only), and their
    OWN latest performance final_score (already self-visible via
    MyPerformancePage.tsx). No employee id is ever accepted here, for any
    role — this is self-only, full stop, with no privileged "view
    anyone's statement" mode (spec §3.4). No RequiresPayrollStepUp: that
    control is for privileged access to someone ELSE's Restricted-tier
    pay data, not self-view of your own (spec §3.2)."""
    employee = get_request_employee(request)
    if employee is None:
        return Response({"detail": "No employee record is associated with this account."}, status=400)

    version = employee.current_version
    job_grade = version.job_grade if version is not None else None

    remuneration = latest_remuneration_for_employee(employee.id)

    pay_band_position = None
    if job_grade is not None and remuneration is not None:
        band = PayBand.objects.filter(job_grade=job_grade).current().first()
        if band is not None:
            salary = remuneration["fixed_remuneration"]
            band_range = band.max_salary - band.min_salary
            percentile = ((salary - band.min_salary) / band_range * 100) if band_range else None
            pay_band_position = {
                "job_grade": job_grade.id,
                "job_grade_code": job_grade.code,
                "min_salary": band.min_salary,
                "mid_salary": band.mid_salary,
                "max_salary": band.max_salary,
                "valid_from": band.valid_from,
                "percentile": percentile,
            }

    elections = (
        BenefitsElection.objects.filter(employee=employee)
        .select_related("benefit")
        .order_by("benefit__name")
    )
    benefits = [
        {
            "benefit_id": election.benefit_id,
            "benefit_name": election.benefit.name,
            "category": election.benefit.category,
            "status": election.status,
            "effective_date": election.effective_date,
        }
        for election in elections
    ]

    return Response({
        "employee": employee.id,
        "job_grade": job_grade.id if job_grade else None,
        "job_grade_code": job_grade.code if job_grade else None,
        "salary": remuneration,
        "pay_band_position": pay_band_position,
        "benefits": benefits,
        "performance_context": latest_final_score(employee.id),
    })
