from django.contrib import admin

from .models import Feedback, Goal, Review, ReviewCycle


@admin.register(ReviewCycle)
class ReviewCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "cycle_type", "status", "start_date", "end_date")
    list_filter = ("status", "cycle_type")


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("employee", "title", "status", "target_date")
    list_filter = ("status",)
    search_fields = ("title", "employee__employee_number")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "review_cycle", "manager", "self_submitted_at", "manager_submitted_at")
    list_filter = ("review_cycle",)
    search_fields = ("employee__employee_number",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("employee", "author", "feedback_type", "created_at")
    list_filter = ("feedback_type",)
    search_fields = ("employee__employee_number",)
