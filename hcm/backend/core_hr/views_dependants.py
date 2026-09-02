"""Dependants and emergency contacts (C2 design spec §2.8, §5.2). Split out
of views.py (HR_Code_report.md M5) -- no behavior change; see that
module's own docstring for the app's overall split."""
from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import viewsets

from .models import Dependant, EmergencyContact
from .permissions import IsSelfOrHRAdmin
from .serializers import DependantSerializer, EmergencyContactSerializer


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
