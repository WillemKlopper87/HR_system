from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Benefit, BenefitsElection, CompProposal, PayBand
from .permissions import IsCompManagerOrHRAdmin, IsCompManagerOrHRAdminOrReadOnly, IsSelfOrCompManagerOrHRAdmin
from .serializers import (
    BenefitSerializer,
    BenefitsElectionSerializer,
    CompProposalSerializer,
    PayBandSerializer,
)
from .services import ApprovalError, approve_proposal, propose_compensation_change, reject_proposal


class PayBandViewSet(viewsets.ModelViewSet):
    queryset = PayBand.objects.select_related("job_grade", "created_by")
    serializer_class = PayBandSerializer
    permission_classes = [IsCompManagerOrHRAdmin]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))


class CompProposalViewSet(viewsets.ModelViewSet):
    """No PATCH on core fields — a proposal is created once via 'propose'
    semantics (see perform_create) and thereafter only moves through the
    approve/reject actions, never edited in place."""

    queryset = CompProposal.objects.select_related(
        "employee", "current_job_grade", "proposed_by", "approved_by"
    )
    serializer_class = CompProposalSerializer
    permission_classes = [IsCompManagerOrHRAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        try:
            serializer.instance = propose_compensation_change(
                employee=serializer.validated_data["employee"],
                proposed_annual_salary=serializer.validated_data["proposed_annual_salary"],
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
