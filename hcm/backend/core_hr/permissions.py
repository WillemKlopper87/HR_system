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


class EmploymentChangePermission(permissions.BasePermission):
    """Coarse gate for EmploymentChangeViewSet (C1 part 3, design spec
    docs/superpowers/specs/2026-08-20-employment-exit-states-design.md
    §8): read is hr_admin + auditor; propose/confirm/cancel are hr_admin
    only. Same coarse-then-per-action shape as
    establishment.permissions.EstablishmentPermission — but there is no
    further per-action narrowing needed here, because the one thing that
    DOES vary by actor identity (tiered types needing a *different*
    hr_admin to confirm, spec §4.2) isn't a role check at all: it's the
    state machine's own same/different-person rule, decided from identity
    alone, so it belongs in exits.py's service layer (400) rather than
    here (403) — see exits.py's module docstring."""

    READ_ROLES = ("hr_admin", "auditor")
    WRITE_ROLES = ("hr_admin",)

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)
