"""Role-adaptive overview dashboard (Wireframe all features spec(4),
"HCM Dashboard Styles.dc.html", Style A -- hybrid workspace). Kept out of
views.py deliberately: that module is already flagged as an oversized
hotspot (HR_Code_report.md M5), and this endpoint's whole job is reading
from every other dashboard rather than owning any data itself, so it
reads more like a composition layer than a views.py addition.

Cross-app data comes through each app's own queries.py read seam
(Architecture-Design.md §4) -- core_hr may not import recruitment/
establishment/policies/ee_reporting/learning models directly, same rule
every other app already follows.

Role bucketing is by the viewer's widest active row-scope grant (all >
own_team > self), not by a hardcoded role-name list, so any role
combination lands in a sensible bucket automatically. This is a
deliberate v1 simplification: recruiter/comp_manager/ee_manager/auditor/
accounting_officer/sysadmin all currently fall into the "employee"
bucket here (their own dedicated dashboards elsewhere in the nav are
unaffected) rather than getting a bespoke KPI/queue set each -- a real
limitation, not an oversight, and the next thing to widen if this proves
out."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from config.settings import CONTRACT_ESCALATION_DAYS, CONTRACT_REMINDER_OFFSETS_DAYS
from ee_reporting.queries import workforce_profile_totals_by_level
from establishment.queries import establishment_summary
from learning.queries import mandatory_training_compliance_summary
from policies.queries import policy_acknowledgment_summary
from rbac_audit.drf import get_request_employee, row_scoped_queryset
from rbac_audit.models import Role
from rbac_audit.permissions import active_roles_for, can_see_unsuppressed_aggregates, is_in_reporting_chain
from rbac_audit.tiers import FieldTier
from recruitment.queries import recruitment_summary

from .models import ContractRenewalDecision, Employee, EmployeeVersion


def _scope_bucket(actor) -> str:
    scopes = set(active_roles_for(actor).values_list("row_scope", flat=True))
    if Role.RowScope.ALL in scopes:
        return "hr_admin"
    if Role.RowScope.OWN_TEAM in scopes:
        return "line_manager"
    return "employee"


def _kpi(label: str, value: str, delta: str, tone: str) -> dict:
    return {"label": label, "value": value, "delta": delta, "tone": tone}


def _queue_item(*, title, meta, ref, age, primary, secondary, href) -> dict:
    return {"title": title, "meta": meta, "ref": ref, "age": age, "primary": primary, "secondary": secondary, "href": href}


def _hr_admin_kpis(today) -> list[dict]:
    total_headcount = EmployeeVersion.objects.current().count()
    est = establishment_summary()
    rec = recruitment_summary()
    pol = policy_acknowledgment_summary()

    vacancy_tone = "bad" if est["vacancy_rate_pct"] >= 10 else "warn" if est["vacancy_rate_pct"] >= 5 else "good"
    ack_tone = "good" if (pol["average_acknowledged_pct"] or 0) >= 80 else "warn"

    return [
        _kpi("Total headcount", str(total_headcount), f"{est['filled']} of {est['funded']} funded posts filled", "neutral"),
        _kpi("Vacancy rate", f"{est['vacancy_rate_pct']}%", f"{est['vacant']} vacant funded posts", vacancy_tone),
        _kpi("Open requisitions", str(rec["open_requisitions"]), "across all departments", "neutral"),
        _kpi(
            "Avg. days to fill",
            str(rec["avg_days_to_fill"]) if rec["avg_days_to_fill"] is not None else "—",
            "from requisition open to hire",
            "neutral",
        ),
        _kpi(
            "Policy acknowledgment",
            f"{pol['average_acknowledged_pct']}%" if pol["average_acknowledged_pct"] is not None else "—",
            "average across published policies",
            ack_tone,
        ),
    ]


def _hr_admin_queue(today) -> list[dict]:
    queue = []
    awaiting_hr_decision = EmployeeVersion.objects.current().filter(
        contract_renewal_decision__status=ContractRenewalDecision.Status.RECOMMENDED
    ).select_related("employee", "contract_renewal_decision")
    for version in awaiting_hr_decision[:5]:
        queue.append(_queue_item(
            title=f"Decide contract renewal · {version.employee.first_name} {version.employee.last_name}",
            meta=f"Recommended {version.contract_renewal_decision.recommended_at.date().isoformat()} · "
                 f"fixed-term ends {version.contract_end_date}",
            ref=f"EV-{version.id}", age="awaiting HR decision",
            primary="Decide", secondary="Open", href="/contract-renewals",
        ))
    open_dq_count = Employee.objects.filter(data_quality_exceptions__resolved_at__isnull=True).distinct().count()
    if open_dq_count:
        queue.append(_queue_item(
            title=f"Data quality · {open_dq_count} open exception{'s' if open_dq_count != 1 else ''}",
            meta="Missing grades, demographics, contract end dates and more",
            ref="DQ", age="open", primary="Open queue", secondary="", href="/data-quality",
        ))
    return queue


def _line_manager_kpis(actor, today) -> list[dict]:
    team = row_scoped_queryset(EmployeeVersion.objects.current(), actor, employee_field="employee")
    team_count = team.count()
    reminder_cutoff = today + timedelta(days=CONTRACT_REMINDER_OFFSETS_DAYS[0])
    contracts_ending = team.filter(
        employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
        contract_end_date__isnull=False,
        contract_end_date__lte=reminder_cutoff,
    ).count()
    return [
        _kpi("Team headcount", str(team_count), "your reporting line", "neutral"),
        _kpi(
            "Contracts ending soon", str(contracts_ending),
            f"within {CONTRACT_REMINDER_OFFSETS_DAYS[0]} days", "warn" if contracts_ending else "good",
        ),
    ]


def _line_manager_queue(actor, today) -> list[dict]:
    queue = []
    escalation_cutoff = today + timedelta(days=CONTRACT_ESCALATION_DAYS)
    team = row_scoped_queryset(EmployeeVersion.objects.current(), actor, employee_field="employee")
    awaiting_recommendation = team.filter(
        employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
        contract_end_date__isnull=False,
        contract_end_date__lte=escalation_cutoff,
        contract_renewal_decision__isnull=True,
    ).select_related("employee")
    for version in awaiting_recommendation[:5]:
        queue.append(_queue_item(
            title=f"Recommend contract renewal · {version.employee.first_name} {version.employee.last_name}",
            meta=f"Fixed-term ends {version.contract_end_date} · your direct report",
            ref=f"EV-{version.id}", age=f"≤{CONTRACT_ESCALATION_DAYS} days left",
            primary="Recommend", secondary="Open", href="/contract-renewals",
        ))
    return queue


def _employee_kpis(actor) -> list[dict]:
    from policies.models import Policy, PolicyAcknowledgment

    published = Policy.objects.filter(status=Policy.Status.PUBLISHED)
    acknowledged_ids = PolicyAcknowledgment.objects.filter(employee=actor).values_list("policy_id", flat=True)
    outstanding = published.exclude(id__in=acknowledged_ids).count()
    return [
        _kpi("Policies to acknowledge", str(outstanding), "", "warn" if outstanding else "good"),
    ]


def _employee_queue(actor) -> list[dict]:
    from policies.models import Policy, PolicyAcknowledgment

    published = Policy.objects.filter(status=Policy.Status.PUBLISHED)
    acknowledged_ids = PolicyAcknowledgment.objects.filter(employee=actor).values_list("policy_id", flat=True)
    queue = []
    for policy in published.exclude(id__in=acknowledged_ids).order_by("title")[:5]:
        queue.append(_queue_item(
            title=f"Acknowledge {policy.title} v{policy.version}",
            meta="Required for all employees", ref=f"POL-{policy.id}", age="outstanding",
            primary="Acknowledge", secondary="Read", href="/my-policies",
        ))
    return queue


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def overview_dashboard(request):
    actor = get_request_employee(request)
    today = timezone.localdate()
    bucket = _scope_bucket(actor)

    if bucket == "hr_admin":
        kpis, queue = _hr_admin_kpis(today), _hr_admin_queue(today)
        scope_note = f"Organisation-wide · {EmployeeVersion.objects.current().count()} active employment versions"
    elif bucket == "line_manager":
        kpis, queue = _line_manager_kpis(actor, today), _line_manager_queue(actor, today)
        scope_note = "Your reporting line · demographics as suppressed aggregates"
    else:
        kpis, queue = _employee_kpis(actor), _employee_queue(actor)
        scope_note = "Your own record and obligations"

    can_see_unsuppressed = can_see_unsuppressed_aggregates(actor, FieldTier.SENSITIVE)

    data = {
        "as_of": today,
        "row_scope": bucket,
        "scope_note": scope_note,
        "kpis": kpis,
        "queue": queue,
        "queue_count": len(queue),
    }

    if bucket in ("hr_admin", "line_manager"):
        team = (
            EmployeeVersion.objects.current()
            if bucket == "hr_admin"
            else row_scoped_queryset(EmployeeVersion.objects.current(), actor, employee_field="employee")
        )
        # "key" is already the department name -- BreakdownRow shape
        # (api/types.ts), same as core_hr.headcount_dashboard's own rows.
        dept_rows = team.values("department__name").annotate(count=Count("id")).order_by("-count")
        data["departments"] = [
            {"key": row["department__name"], "count": row["count"]}
            for row in dept_rows if row["department__name"]
        ][:6]

    if bucket == "hr_admin":
        data["occupational_levels"] = workforce_profile_totals_by_level(today, suppress=not can_see_unsuppressed)
        data["small_cell_suppression_applied"] = not can_see_unsuppressed
        data["recruitment_funnel"] = recruitment_summary()["by_stage"]
        data["training_compliance"] = mandatory_training_compliance_summary(as_of=today)
        data["policy_acknowledgment"] = policy_acknowledgment_summary()["policies"][:4]

    return Response(data)
