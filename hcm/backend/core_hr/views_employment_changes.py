"""The employment-exit state machine's HTTP surface. Split out of views.py
(HR_Code_report.md M5) -- no behavior change; see that module's own
docstring for the app's overall split."""
from __future__ import annotations

from rbac_audit.drf import get_request_employee, int_query_param
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .exits import EmploymentChangeError, cancel_employment_change, confirm_employment_change, propose_employment_change
from .models import EmploymentChange
from .permissions import EmploymentChangePermission
from .serializers import EmploymentChangeSerializer


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
