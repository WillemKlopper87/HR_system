from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsRecruiterOrHRAdmin(permissions.BasePermission):
    """RBAC-Roles.md: requisitions/applicants/offers are recruiter +
    hr_admin territory, both row_scope=all — unlike core_hr's viewsets
    this doesn't need RowScopePermission's per-object row-scope machinery,
    since there's no narrower-scoped role touching recruitment data."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        employee = get_request_employee(request)
        return has_role(employee, "recruiter") or has_role(employee, "hr_admin")
