from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsHRAdmin(permissions.BasePermission):
    """Gate for endpoints RBAC-Roles.md reserves to hr_admin specifically
    (org-structure writes, the data-quality queue) — narrower than the
    generic field-tier grants in rbac_audit.tiers, since these aren't
    employee-record reads/writes."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_role(get_request_employee(request), "hr_admin")


class IsHRAdminOrReadOnly(permissions.BasePermission):
    """Any authenticated employee can read org-structure reference data
    (departments, grades, locations — needed for dropdowns everywhere);
    only hr_admin can create/update/delete it."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return has_role(get_request_employee(request), "hr_admin")
