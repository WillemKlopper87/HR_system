# hcm/backend/establishment/permissions.py
from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class EstablishmentPermission(permissions.BasePermission):
    """Coarse gate, fine-grained per-action in views.py -- same shape as
    ee_reporting.permissions.EEReportingPermission. WRITE_ROLES lets any of
    the three workflow roles reach a POST at this layer; which specific
    action (propose/submit/revise vs. a decide step) each one may actually
    perform is enforced per-action in views.py."""

    READ_ROLES = ("hr_admin", "comp_manager", "accounting_officer", "auditor", "recruiter")
    WRITE_ROLES = ("hr_admin", "comp_manager", "accounting_officer")

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)
