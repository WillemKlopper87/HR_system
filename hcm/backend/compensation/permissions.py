from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsCompManagerOrHRAdmin(permissions.BasePermission):
    """Sprint 10 acceptance criterion: "Pay-data visibility restricted to
    comp manager/HR admin roles only (strict RBAC)." Applied to the whole
    module — pay bands, proposals, and the benefits catalog alike — not
    just individual employee pay figures."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        employee = get_request_employee(request)
        return has_role(employee, "comp_manager") or has_role(employee, "hr_admin")
