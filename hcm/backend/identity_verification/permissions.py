from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class IsSelfOrHRAdmin(permissions.BasePermission):
    """Biometric/attendance data doesn't fit the generic P/I/S/R tier
    grants (POPIA treats biometric data as a stricter category than this
    system's highest generic tier) — gated explicitly here, the same
    documented-exception pattern as recruitment.Offer/performance.Review/
    compensation/assessments. Self access (an employee enrolling or
    checking in on their own identity) plus hr_admin (investigation/
    review) covers this module's surface; auditor gets read-only,
    matching its "read-only everywhere" charter (RBAC-Roles.md)."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if has_role(employee, "hr_admin"):
            return True
        if request.method in permissions.SAFE_METHODS and has_role(employee, "auditor"):
            return True
        return employee.id == obj.employee_id
