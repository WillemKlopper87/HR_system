from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Benefit, BenefitsElection, CompCycle, CompProposal, PayBand


@admin.register(PayBand)
class PayBandAdmin(SimpleHistoryAdmin):
    list_display = ("job_grade", "min_salary", "mid_salary", "max_salary", "valid_from", "valid_to")
    list_filter = ("job_grade",)


@admin.register(CompCycle)
class CompCycleAdmin(SimpleHistoryAdmin):
    list_display = ("name", "period_start", "period_end", "budget_amount", "department", "status")
    list_filter = ("status", "department")


@admin.register(CompProposal)
class CompProposalAdmin(SimpleHistoryAdmin):
    list_display = (
        "employee", "proposal_type", "proposed_annual_salary", "bonus_amount", "status", "requires_override",
        "exceeds_cycle_budget", "cycle", "proposed_by", "approved_by",
    )
    list_filter = ("status", "proposal_type", "requires_override", "exceeds_cycle_budget")
    search_fields = ("employee__employee_number", "employee__preferred_name")


@admin.register(Benefit)
class BenefitAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "active")
    list_filter = ("category", "active")
    search_fields = ("name",)


@admin.register(BenefitsElection)
class BenefitsElectionAdmin(admin.ModelAdmin):
    list_display = ("employee", "benefit", "status", "effective_date")
    list_filter = ("status", "benefit")
    search_fields = ("employee__employee_number",)
