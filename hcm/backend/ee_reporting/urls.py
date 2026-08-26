from django.urls import path
from rest_framework.routers import DefaultRouter

from .dashboards import equity_dashboard
from .views import (
    EEForumMeetingViewSet,
    EEForumMemberViewSet,
    EEPlanMeasureViewSet,
    EEPlanProgressSnapshotViewSet,
    EEPlanViewSet,
    EEQuestionnaireViewSet,
    EEReportViewSet,
    EmployerConfigViewSet,
    RemunerationRecordViewSet,
)

router = DefaultRouter()
router.register("employer-config", EmployerConfigViewSet, basename="employer-config")
router.register("ee-plans", EEPlanViewSet, basename="ee-plan")
router.register("ee-questionnaires", EEQuestionnaireViewSet, basename="ee-questionnaire")
router.register("remuneration-records", RemunerationRecordViewSet, basename="remuneration-record")
router.register("ee-reports", EEReportViewSet, basename="ee-report")
router.register("ee-forum-members", EEForumMemberViewSet, basename="ee-forum-member")
router.register("ee-forum-meetings", EEForumMeetingViewSet, basename="ee-forum-meeting")
router.register("ee-plan-measures", EEPlanMeasureViewSet, basename="ee-plan-measure")
router.register("ee-plan-snapshots", EEPlanProgressSnapshotViewSet, basename="ee-plan-snapshot")

urlpatterns = router.urls + [
    path("dashboards/equity/", equity_dashboard, name="equity-dashboard"),
]
