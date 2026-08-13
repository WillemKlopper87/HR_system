from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CertificationViewSet,
    EmployeeSkillViewSet,
    SkillViewSet,
    TrainingRecordViewSet,
    skills_inventory,
    team_development,
    wsp_atr_export,
)

router = DefaultRouter()
router.register("skills", SkillViewSet, basename="skill")
router.register("employee-skills", EmployeeSkillViewSet, basename="employee-skill")
router.register("certifications", CertificationViewSet, basename="certification")
router.register("training-records", TrainingRecordViewSet, basename="training-record")

urlpatterns = router.urls + [
    path("dashboards/learning/skills-inventory/", skills_inventory, name="skills-inventory"),
    path("dashboards/learning/team-development/", team_development, name="team-development"),
    path("dashboards/learning/wsp-atr-export/", wsp_atr_export, name="wsp-atr-export"),
]
