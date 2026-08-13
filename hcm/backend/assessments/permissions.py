from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class CanAccessAssessmentAssignment(permissions.BasePermission):
    """Assessment results carry the same sensitivity as demographic data
    (Architecture-Design.md §5.2) but span two subject types with
    different access rules (RBAC-Roles.md: recruiter "no access to
    employee performance/comp modules"; line_manager has no assessments
    carve-out the way it does for reviews/goals) — too much divergence for
    the generic tiered-serializer/row-scope helpers, which assume a single
    row-scope model. Gated explicitly here instead, mirroring the
    documented exception already used for recruitment.Offer and
    performance.Review/Feedback.

    Read: the subject employee themself, hr_admin, auditor (read-only
    everywhere per RBAC-Roles.md), ee_manager for employee-subject rows,
    recruiter for applicant-subject rows. Write (assign): hr_admin,
    ee_manager (employee subject only), recruiter (applicant subject
    only) — enforced precisely in AssessmentAssignmentSerializer.validate,
    since which subject type is being written isn't known until then."""

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return has_role(employee, "hr_admin") or has_role(employee, "ee_manager") or has_role(employee, "recruiter")

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if has_role(employee, "hr_admin") or has_role(employee, "auditor"):
            return True
        if obj.employee_id is not None:
            if employee.id == obj.employee_id:
                return True
            return has_role(employee, "ee_manager")
        return has_role(employee, "recruiter")
