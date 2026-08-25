from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class CriticalPostPermission(permissions.BasePermission):
    """Coarse gate for CriticalPostViewSet (spec §5.1): read is the same
    audience that can already see establishment.Position at all (the flag
    is Position-adjacent metadata, not the sensitive nominee list); every
    write is hr_admin only. Same shape as onboarding's
    ChecklistTemplatePermission."""

    READ_ROLES = ("hr_admin", "comp_manager", "accounting_officer", "auditor", "recruiter")
    WRITE_ROLES = ("hr_admin",)

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)


class SuccessionCandidatePermission(permissions.BasePermission):
    """Coarse gate for SuccessionCandidateViewSet (spec §5.2): hr_admin
    reads and writes; auditor reads only; every other role -- including the
    nominated employee themself and their line_manager -- gets 403 on both
    list and retrieve. No self-scope carve-out anywhere (spec §2.6)."""

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return has_role(employee, "hr_admin") or has_role(employee, "auditor")
        return has_role(employee, "hr_admin")
