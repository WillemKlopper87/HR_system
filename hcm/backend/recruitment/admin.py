from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Applicant, ApplicantStageEvent, Offer, Requisition


class ApplicantInline(admin.TabularInline):
    model = Applicant
    extra = 0
    fields = ("first_name", "last_name", "email", "current_stage")
    show_change_link = True
    can_delete = False


@admin.register(Requisition)
class RequisitionAdmin(SimpleHistoryAdmin):
    list_display = ("title", "department", "status", "headcount", "hiring_manager")
    list_filter = ("status", "department")
    search_fields = ("title",)
    inlines = [ApplicantInline]


@admin.register(Applicant)
class ApplicantAdmin(SimpleHistoryAdmin):
    list_display = ("first_name", "last_name", "email", "requisition", "current_stage")
    list_filter = ("current_stage",)
    search_fields = ("first_name", "last_name", "email")


@admin.register(ApplicantStageEvent)
class ApplicantStageEventAdmin(admin.ModelAdmin):
    list_display = ("applicant", "from_stage", "to_stage", "changed_by", "created_at")
    list_filter = ("to_stage",)


@admin.register(Offer)
class OfferAdmin(SimpleHistoryAdmin):
    list_display = ("applicant", "status", "proposed_annual_salary", "proposed_by", "approved_by")
    list_filter = ("status",)
