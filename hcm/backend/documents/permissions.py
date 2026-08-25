from __future__ import annotations

from core_hr.permissions import is_self_or_hr_admin
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import can_access_tier_for_target, has_role
from rest_framework import permissions


class EmployeeDocumentPermission(permissions.BasePermission):
    """Design spec §5.1: writes are self-or-hr_admin only (no line_manager,
    no other all-scope role — uploading/deleting a document is HR
    administration); reads are row-tier gated via
    can_access_tier_for_target, which is what lets ee_manager/comp_manager/
    line_manager see the tiers their existing generic grants already cover
    (see the spec table) without special-casing each role here."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_access_tier_for_target(employee, obj.employee, obj.tier, mode="read")
        return is_self_or_hr_admin(employee, obj.employee)


class DataSubjectRequestPermission(permissions.BasePermission):
    """Design spec §5.3: create is self-or-hr_admin (an hr_admin may file
    on behalf of someone who can no longer log in — see the model
    docstring); list/read row-scope is handled in the viewset's
    get_queryset (self, hr_admin all, auditor all — same shape as every
    other row-scoped viewset); complete/decline are hr_admin-only, checked
    directly in the view actions (same shape as
    onboarding.ChecklistInstancePermission's split for actions that need
    more than a blanket role check)."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            # Self, hr_admin, or auditor (read-only everywhere) — NOT the
            # generic row-scope=all set (that would also hand every other
            # all-scope role, e.g. comp_manager/recruiter, detail access to
            # someone else's POPIA request, which the spec table §5.3
            # deliberately doesn't grant).
            return is_self_or_hr_admin(employee, obj.employee) or has_role(employee, "auditor")
        return is_self_or_hr_admin(employee, obj.employee)
