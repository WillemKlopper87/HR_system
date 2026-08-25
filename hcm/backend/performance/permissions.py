"""Access rules for performance agreements (PC-1, ADR-010).

Deliberately an explicit permission class rather than the generic P/I/S/R
tier path — same reasoning the `Review` model already carries: line_manager's
blanket Sensitive-tier grant is closed (aggregate-only, for demographics) yet
RBAC-Roles.md says a line manager individually "sees own team's reviews/
goals". Row scope is the real gate here, plus three module facts:

* the **Head** on the agreement is snapshotted, and an active
  `SigningDelegation` lets a designated person act in their place — neither is
  expressible as a row-scope rule, so both are checked here;
* **hr_admin** reads everything and administers periods/templates, but never
  signs for anyone (the user's process: HR receives the signed document);
* **auditor** is read-only everywhere, as everywhere else.
"""
from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role, is_in_reporting_chain
from rest_framework import permissions

from .models import PerformanceAgreement
from .services import active_delegation

ADMIN_ROLES = ("hr_admin",)
READ_ALL_ROLES = ("hr_admin", "auditor")


def is_admin(employee) -> bool:
    return any(has_role(employee, role) for role in ADMIN_ROLES)


def can_read_all(employee) -> bool:
    return any(has_role(employee, role) for role in READ_ALL_ROLES)


def is_head_of(agreement: PerformanceAgreement, employee) -> bool:
    """The snapshotted Head, an active delegate of that Head, or anyone above
    the employee in today's reporting chain (a skip-level manager legitimately
    supervises the conversation even though only the Head signs)."""
    if employee is None:
        return False
    if agreement.head_id and agreement.head_id == employee.pk:
        return True
    if agreement.head_id and active_delegation(agreement.head, employee) is not None:
        return True
    return is_in_reporting_chain(employee, agreement.employee)


def can_view_agreement(agreement: PerformanceAgreement, employee) -> bool:
    if employee is None:
        return False
    return (
        agreement.employee_id == employee.pk
        or can_read_all(employee)
        or is_head_of(agreement, employee)
    )


def can_edit_agreement(agreement: PerformanceAgreement, employee) -> bool:
    """Content edits while the agreement is still open: the employee and the
    Head work on it together (the user's process is a conversation, then a
    signature); hr_admin can correct anything; auditor never writes."""
    if employee is None or not agreement.is_editable:
        return False
    if has_role(employee, "auditor") and not is_admin(employee):
        return False
    return agreement.employee_id == employee.pk or is_admin(employee) or is_head_of(agreement, employee)


def can_act_on_agreement(agreement: PerformanceAgreement, employee) -> bool:
    """"May you act on this agreement at all" — the subject, the Head (or an
    active delegate), hr_admin. Deliberately *not* gated on `is_editable`
    (unlike `can_edit_agreement`): PC-2's mid-year/final stage fields and
    evidence are writable well past contracting's own draft/returned window,
    and it's the stage-specific rules (STAGE_ELEMENT_FIELDS, STAGE_FLOW) that
    decide *which* action is allowed right now, not this gate."""
    if employee is None:
        return False
    if has_role(employee, "auditor") and not is_admin(employee):
        return False
    return agreement.employee_id == employee.pk or is_admin(employee) or is_head_of(agreement, employee)


class PerformanceAgreementPermission(permissions.IsAuthenticated):
    """Object-level gate; per-action authority (submit/return/approve/sign)
    lives in the service layer so every entry point obeys it."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if request.method in permissions.SAFE_METHODS:
            return can_view_agreement(obj, employee)
        return can_act_on_agreement(obj, employee)


class IsHRAdminOrReadOnlyForPerformance(permissions.IsAuthenticated):
    """Periods and templates: everyone authenticated may read (staff need to
    see the deadlines that apply to them); only hr_admin may write."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_admin(employee)


class CalibrationSessionPermission(permissions.IsAuthenticated):
    """Design spec §5.1: a department-wide committee record is a comparative
    judgement about a group of named individuals, the same risk shape as
    succession's `SuccessionCandidate` (spec §2.6 there) -- hr_admin/auditor
    only, no self/team browsing. One agreement's own outcome still reaches
    its subject/Head via the nested `calibration_adjustments` field on
    `PerformanceAgreementSerializer`, gated by the agreement's own
    permission instead."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_read_all(employee)
        return is_admin(employee)

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return can_read_all(employee)
        return is_admin(employee)


class Feedback360RaterPermission(permissions.IsAuthenticated):
    """Broad "is this row reachable at all" gate (design spec §5.2): the
    parent agreement's own audience (self/Head/delegate/hr_admin/auditor —
    `can_view_agreement`), or the named rater looking at their own slot even
    when they have no other access to the agreement (a plain peer/direct-
    report rater usually can't view the agreement itself at all). The finer
    "may you approve/decline/respond" authority test lives in each action in
    views_feedback360.py, the same two-layer shape return_agreement /
    approve_agreement already use in views_agreements.py."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        return can_view_agreement(obj.request.agreement, employee) or employee.pk == obj.rater_id


class SigningDelegationPermission(permissions.IsAuthenticated):
    """A Head delegates their own signing authority; hr_admin may do it on
    their behalf (someone must be able to fix it when the Head is already
    unreachable — the case the delegation exists for)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return get_request_employee(request) is not None

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        if employee is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return obj.delegator_id == employee.pk or obj.delegate_id == employee.pk or can_read_all(employee)
        return obj.delegator_id == employee.pk or is_admin(employee)
