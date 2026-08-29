from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DataQualityExceptionViewSet,
    DependantViewSet,
    DepartmentViewSet,
    EmergencyContactViewSet,
    EmployeeVersionViewSet,
    EmployeeViewSet,
    EmploymentChangeViewSet,
    JobGradeViewSet,
    LocationViewSet,
    OccupationalLevelViewSet,
    ExitInterviewViewSet,
    ProbationPeriodViewSet,
    ProbationReviewViewSet,
    exit_interview_dashboard,
    headcount_dashboard,
    probation_completion_dashboard,
)
from .views_overview import overview_dashboard

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("employee-versions", EmployeeVersionViewSet, basename="employee-version")
router.register("employment-changes", EmploymentChangeViewSet, basename="employment-change")
router.register("departments", DepartmentViewSet, basename="department")
router.register("occupational-levels", OccupationalLevelViewSet, basename="occupational-level")
router.register("job-grades", JobGradeViewSet, basename="job-grade")
router.register("locations", LocationViewSet, basename="location")
router.register("data-quality-exceptions", DataQualityExceptionViewSet, basename="data-quality-exception")
router.register("dependants", DependantViewSet, basename="dependant")
router.register("emergency-contacts", EmergencyContactViewSet, basename="emergency-contact")
router.register("probation-periods", ProbationPeriodViewSet, basename="probation-period")
router.register("probation-reviews", ProbationReviewViewSet, basename="probation-review")
router.register("exit-interviews", ExitInterviewViewSet, basename="exit-interview")

urlpatterns = router.urls + [
    path("dashboards/overview/", overview_dashboard, name="overview-dashboard"),
    path("dashboards/headcount/", headcount_dashboard, name="headcount-dashboard"),
    path("dashboards/probation/", probation_completion_dashboard, name="probation-dashboard"),
    path("dashboards/exit-interviews/", exit_interview_dashboard, name="exit-interview-dashboard"),
]
