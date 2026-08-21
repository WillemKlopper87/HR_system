from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DataQualityExceptionViewSet,
    DepartmentViewSet,
    EmployeeVersionViewSet,
    EmployeeViewSet,
    EmploymentChangeViewSet,
    JobGradeViewSet,
    LocationViewSet,
    OccupationalLevelViewSet,
    headcount_dashboard,
)

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("employee-versions", EmployeeVersionViewSet, basename="employee-version")
router.register("employment-changes", EmploymentChangeViewSet, basename="employment-change")
router.register("departments", DepartmentViewSet, basename="department")
router.register("occupational-levels", OccupationalLevelViewSet, basename="occupational-level")
router.register("job-grades", JobGradeViewSet, basename="job-grade")
router.register("locations", LocationViewSet, basename="location")
router.register("data-quality-exceptions", DataQualityExceptionViewSet, basename="data-quality-exception")

urlpatterns = router.urls + [
    path("dashboards/headcount/", headcount_dashboard, name="headcount-dashboard"),
]
