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


def _is_recruiter_or_hr_admin(employee) -> bool:
    return has_role(employee, "recruiter") or has_role(employee, "hr_admin")


class IsRecruiterOrHRAdminOrAssignedInterviewer(permissions.BasePermission):
    """C6 design spec §3.1: recruiter/hr_admin manage the whole interview
    pipeline; an assigned interviewer (a row-level, not role-level, grant —
    "assigned interviewer" isn't an RBAC-Roles.md role, any employee can
    hold it for one session and not another) gets SAFE_METHODS-only access
    to sessions they're actually on the panel for. List-level row-filtering
    happens in InterviewSessionViewSet.get_queryset, not here."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if _is_recruiter_or_hr_admin(employee):
            return True
        if request.method not in permissions.SAFE_METHODS:
            return False
        return obj.interviewers.filter(pk=employee.pk).exists()


class InterviewScorecardPermission(permissions.BasePermission):
    """C6 design spec §3.2: only the named interviewer may author/update
    their own scorecard (no proxy-entry, not even by hr_admin); read access
    is recruiter/hr_admin (always) or any interviewer on the same session
    (own row always, peers' rows subject to the blind-review masking in
    InterviewScorecardSerializer.to_representation, not enforced here —
    this class only decides whether the row is reachable at all, not which
    of its fields render)."""

    def has_permission(self, request, view):
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            if _is_recruiter_or_hr_admin(employee):
                return True
            return obj.session.interviewers.filter(pk=employee.pk).exists()
        return obj.interviewer_id == employee.id
