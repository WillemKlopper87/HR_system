from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Benefit, BenefitsElection, CompProposal, PayBand
from .permissions import IsCompManagerOrHRAdmin
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
    queryset = Benefit.objects.all()
    serializer_class = BenefitSerializer
    permission_classes = [IsCompManagerOrHRAdmin]


class BenefitsElectionViewSet(viewsets.ModelViewSet):
    queryset = BenefitsElection.objects.select_related("employee", "benefit")
    serializer_class = BenefitsElectionSerializer
    permission_classes = [IsCompManagerOrHRAdmin]
