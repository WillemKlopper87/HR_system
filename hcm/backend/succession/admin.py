from django.contrib import admin

from .models import CriticalPost, SuccessionCandidate


@admin.register(CriticalPost)
class CriticalPostAdmin(admin.ModelAdmin):
    list_display = ("position", "active", "flagged_by", "created_at")
    list_filter = ("active",)
    search_fields = ("position__post_number", "position__title")


@admin.register(SuccessionCandidate)
class SuccessionCandidateAdmin(admin.ModelAdmin):
    list_display = ("critical_post", "employee", "readiness", "active", "nominated_by")
    list_filter = ("readiness", "active")
