from __future__ import annotations

from .models import Role, RoleAssignment, RoleFieldTierGrant
from .tiers import FieldTier


def active_roles_for(employee):
    if employee is None:
        return Role.objects.none()
    active_role_ids = RoleAssignment.objects.filter(
        employee=employee, revoked_at__isnull=True, role__active=True
    ).values_list("role_id", flat=True)
    return Role.objects.filter(id__in=active_role_ids)


def can_access_tier(employee, tier: str, *, mode: str = "read") -> bool:
    """mode: 'read' or 'write'. Public-tier fields are always accessible."""
    if tier == FieldTier.PUBLIC:
        return True
    roles = active_roles_for(employee)
    grant_field = "can_read" if mode == "read" else "can_write"
    return RoleFieldTierGrant.objects.filter(role__in=roles, tier=tier, **{grant_field: True}).exists()


def is_in_reporting_chain(manager_employee, target_employee, *, max_depth: int = 20) -> bool:
    """True if target_employee reports, directly or indirectly, to
    manager_employee as at today."""
    if manager_employee is None or target_employee is None:
        return False
    version = target_employee.current_version
    depth = 0
    while version is not None and version.manager_id is not None and depth < max_depth:
        if version.manager_id == manager_employee.id:
            return True
        version = version.manager.current_version
        depth += 1
    return False


def has_row_access(employee, target_employee) -> bool:
    """Row-scope check (all/own_team/self) — RBAC-Roles.md. Any one active
    role granting access is sufficient. Self-access is granted via the
    base 'employee' role (row_scope=self) every employee holds — not
    special-cased here — so a line_manager-only assignment correctly does
    NOT imply self-access on its own."""
    if employee is None or target_employee is None:
        return False
    for role in active_roles_for(employee):
        if role.row_scope == Role.RowScope.ALL:
            return True
        if role.row_scope == Role.RowScope.SELF and employee.id == target_employee.id:
            return True
        if role.row_scope == Role.RowScope.OWN_TEAM and is_in_reporting_chain(employee, target_employee):
            return True
    return False
