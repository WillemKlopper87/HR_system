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


def can_see_unsuppressed_aggregates(employee, tier: str = FieldTier.SENSITIVE) -> bool:
    """True if the employee holds an ALL-row-scope role with tier-level
    read access — the bar for viewing org-wide demographic aggregates
    without small-cell suppression (RBAC-Roles.md standing rule 1 / gap
    C6). Deliberately NOT can_access_tier: the base 'employee' role also
    grants Sensitive-tier read, but only for the employee's own record
    (self row-scope) — that must never unlock suppression on an aggregate
    spanning everyone, e.g. for a line_manager who also holds the base role."""
    if tier == FieldTier.PUBLIC:
        return True
    for role in active_roles_for(employee):
        if role.row_scope != Role.RowScope.ALL:
            continue
        if RoleFieldTierGrant.objects.filter(role=role, tier=tier, can_read=True).exists():
            return True
    return False


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


def _role_covers_target(role, employee, target_employee) -> bool:
    if role.row_scope == Role.RowScope.ALL:
        return True
    if role.row_scope == Role.RowScope.SELF:
        return employee.id == target_employee.id
    if role.row_scope == Role.RowScope.OWN_TEAM:
        return is_in_reporting_chain(employee, target_employee)
    return False


def has_row_access(employee, target_employee) -> bool:
    """Row-scope check (all/own_team/self) — RBAC-Roles.md. Any one active
    role granting access is sufficient. Self-access is granted via the
    base 'employee' role (row_scope=self) every employee holds — not
    special-cased here — so a line_manager-only assignment correctly does
    NOT imply self-access on its own."""
    if employee is None or target_employee is None:
        return False
    return any(_role_covers_target(role, employee, target_employee) for role in active_roles_for(employee))


def can_access_tier_for_target(employee, target_employee, tier: str, *, mode: str = "read") -> bool:
    """Field-tier access for one SPECIFIC record — not can_access_tier's
    "does this employee hold this grant via ANY role at all" check. A
    role's tier grant only counts here if that SAME role's row-scope also
    covers target_employee.

    Without this, the base 'employee' role (self row-scope, S:read=True so
    people can see their own sensitive fields) leaks Sensitive-tier read
    onto every record reachable via a DIFFERENT, wider-scoped role the same
    person holds — e.g. a line_manager, who also holds the base role for
    their own ESS access, would see their reports' race/gender/disability
    individually. RBAC-Roles.md reserves that to hr_admin/ee_manager/
    auditor; line_manager gets aggregate-only demographic visibility,
    never per-record (see can_see_unsuppressed_aggregates)."""
    if tier == FieldTier.PUBLIC:
        return True
    if employee is None or target_employee is None:
        return False
    covering_roles = [r for r in active_roles_for(employee) if _role_covers_target(r, employee, target_employee)]
    if not covering_roles:
        return False
    grant_field = "can_read" if mode == "read" else "can_write"
    return RoleFieldTierGrant.objects.filter(role__in=covering_roles, tier=tier, **{grant_field: True}).exists()
