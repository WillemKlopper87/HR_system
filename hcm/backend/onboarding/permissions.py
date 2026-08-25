from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class ChecklistTemplatePermission(permissions.BasePermission):
    """Coarse gate for ChecklistTemplateViewSet/ChecklistTemplateItemViewSet
    (design spec section 7): read is hr_admin + auditor; every write is
    hr_admin only. Same shape as core_hr.permissions.EmploymentChangePermission
    -- template content isn't something a line manager or employee has a
    standing reason to browse, only their own checklist instance (see
    ChecklistInstancePermission below)."""

    READ_ROLES = ("hr_admin", "auditor")
    WRITE_ROLES = ("hr_admin",)

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)


class ChecklistInstancePermission(permissions.BasePermission):
    """Coarse gate for ChecklistInstanceViewSet/ChecklistInstanceItemViewSet
    (design spec section 7): any authenticated employee may attempt a read
    (the row-level narrowing -- hr_admin/auditor see everything, a
    line_manager sees their reporting chain, everyone else sees only their
    own record -- is done in each viewset's get_queryset, mirroring how
    EmployeeVersion's nested contract_renewal_decision read gate is a
    row-relational check rather than a blanket permission class).

    Manually creating an instance is hr_admin only. Completing/reopening an
    item is NOT decided here -- like exits.py's tiered-confirm rule, it
    needs the specific item's owner_role plus the actor's relationship to
    the employee, so ChecklistInstanceItemViewSet's complete/reopen actions
    check it themselves and return 403 directly."""

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method not in permissions.SAFE_METHODS and view.action == "create":
            return has_role(employee, "hr_admin")
        return True
