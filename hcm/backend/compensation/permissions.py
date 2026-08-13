from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsCompManagerOrHRAdmin(permissions.BasePermission):
    """Sprint 10 acceptance criterion: "Pay-data visibility restricted to
    comp manager/HR admin roles only (strict RBAC)." Applied to pay bands
    and comp proposals — genuine pay figures, unlike the benefits catalog
    below which Sprint 15 opens up for browsing."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        employee = get_request_employee(request)
        return has_role(employee, "comp_manager") or has_role(employee, "hr_admin")


class IsCompManagerOrHRAdminOrReadOnly(permissions.BasePermission):
    """Sprint 15 (ESS): every employee needs to browse the benefits catalog
    to make their own elections — same "read-open reference data, admin-
    only writes" shape as core_hr.IsHRAdminOrReadOnly."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        employee = get_request_employee(request)
        return has_role(employee, "comp_manager") or has_role(employee, "hr_admin")


class IsSelfOrCompManagerOrHRAdmin(permissions.BasePermission):
    """Sprint 15 (ESS): an employee manages their OWN benefits elections;
    comp_manager/hr_admin can record/adjust anyone's, same as they always
    could. Same shape as identity_verification.IsSelfOrHRAdmin — object-
    level self-or-privileged check, not the generic row-scope machinery
    (BenefitsElection has no row-scope-bearing role of its own)."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if has_role(employee, "comp_manager") or has_role(employee, "hr_admin"):
            return True
        return obj.employee_id == employee.id
