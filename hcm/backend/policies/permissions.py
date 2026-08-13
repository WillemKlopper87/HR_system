from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsHRAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_role(get_request_employee(request), "hr_admin")


class IsHRAdminOrReadOnly(permissions.BasePermission):
    """Every employee needs to read the library to acknowledge policies;
    only hr_admin manages it. Same shape as core_hr.IsHRAdminOrReadOnly —
    kept module-local rather than imported, matching this codebase's
    established convention of not sharing permission classes across
    modules even when logically identical (compensation defined its own
    IsCompManagerOrHRAdminOrReadOnly rather than importing core_hr's)."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return has_role(get_request_employee(request), "hr_admin")


class IsSelfOrHRAdmin(permissions.BasePermission):
    """Same shape as identity_verification.IsSelfOrHRAdmin — object-level
    self-or-hr_admin read access. Acknowledgment CREATION is always
    self-only regardless of role (see PolicyAcknowledgmentViewSet); this
    class only governs read/list access to existing acknowledgments."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if has_role(employee, "hr_admin"):
            return True
        return obj.employee_id == employee.id
