from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Benefit, BenefitsElection, CompProposal, PayBand


@admin.register(PayBand)
class PayBandAdmin(SimpleHistoryAdmin):
    list_display = ("job_grade", "min_salary", "mid_salary", "max_salary", "valid_from", "valid_to")
    list_filter = ("job_grade",)


@admin.register(CompProposal)
class CompProposalAdmin(SimpleHistoryAdmin):
    list_display = ("employee", "proposed_annual_salary", "status", "requires_override", "proposed_by", "approved_by")
    list_filter = ("status", "requires_override")
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
