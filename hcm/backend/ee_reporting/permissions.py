from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class EEReportingPermission(permissions.BasePermission):
    """EE reporting spans a document workflow (draft -> EE manager review
    -> Accounting Officer sign-off) across multiple new/repurposed roles,
    not a single row-scope model — same "dedicated explicit permission
    class" pattern as assessments/identity_verification rather than the
    generic P/I/S/R tiers, which weren't designed around an approval
    chain.

    Read: hr_admin, ee_manager, accounting_officer, auditor (read-only
    everywhere). Write: any of the three non-auditor module roles may
    reach a POST action at this coarse-grained layer — WHICH action
    they're actually allowed to perform (generate/submit/config-write vs.
    the ee_review step vs. the sign_off step) is enforced per-action in
    views.py, since each of those needs one specific role, not "any
    write role". This mirrors assessments.CanAccessAssessmentAssignment's
    shape: a broad permission-class gate plus fine-grained in-view
    checks, rather than trying to encode a 3-role approval chain into one
    generic permission class."""

    READ_ROLES = ("hr_admin", "ee_manager", "accounting_officer", "auditor")
    WRITE_ROLES = ("hr_admin", "ee_manager", "accounting_officer")

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)


class RemunerationRecordPermission(EEReportingPermission):
    """Raw per-employee remuneration is Restricted-tier payroll data
    (Data-Dictionary.md), not an EE *document*: RBAC-Roles.md gives
    ee_manager "no pay access" and accounting_officer no standing S/R access
    outside the sign-off action. So this endpoint is narrower than the rest
    of the module — hr_admin reads and imports, auditor reads (R column = R,
    every read audited), nobody else. EEA4 generation reads the table at the
    ORM layer (services.py::generate_report), so ee_manager's review and the
    Accounting Officer's sign-off are unaffected. RequiresPayrollStepUp
    (ADR-009) still layers on top. Found by the H2 access-matrix sweep."""

    READ_ROLES = ("hr_admin", "auditor")
    WRITE_ROLES = ("hr_admin",)
