from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CertificationViewSet,
    CourseRequirementViewSet,
    CourseViewSet,
    EmployeeSkillViewSet,
    SkillViewSet,
    TrainingRecordViewSet,
    skills_inventory,
    team_development,
    training_compliance_dashboard,
    training_compliance_overdue,
    wsp_atr_export,
)

router = DefaultRouter()
router.register("skills", SkillViewSet, basename="skill")
router.register("employee-skills", EmployeeSkillViewSet, basename="employee-skill")
router.register("certifications", CertificationViewSet, basename="certification")
router.register("training-records", TrainingRecordViewSet, basename="training-record")
router.register("courses", CourseViewSet, basename="course")
router.register("course-requirements", CourseRequirementViewSet, basename="course-requirement")

urlpatterns = router.urls + [
    path("dashboards/learning/skills-inventory/", skills_inventory, name="skills-inventory"),
    path("dashboards/learning/team-development/", team_development, name="team-development"),
    path("dashboards/learning/wsp-atr-export/", wsp_atr_export, name="wsp-atr-export"),
    path("dashboards/learning/training-compliance/", training_compliance_dashboard, name="training-compliance"),
    path(
        "dashboards/learning/training-compliance/overdue/",
        training_compliance_overdue,
        name="training-compliance-overdue",
    ),
]
