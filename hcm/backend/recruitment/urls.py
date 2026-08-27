from django.urls import path
from rest_framework.routers import DefaultRouter

from .careers import PublicPostingViewSet, careers_apply
from .views import (
    ApplicantViewSet,
    BackgroundCheckViewSet,
    InterviewScorecardViewSet,
    InterviewSessionViewSet,
    OfferViewSet,
    RequisitionViewSet,
    recruitment_dashboard,
    recruitment_funnel_by_demographic,
)

router = DefaultRouter()
router.register("requisitions", RequisitionViewSet, basename="requisition")
router.register("applicants", ApplicantViewSet, basename="applicant")
router.register("offers", OfferViewSet, basename="offer")
router.register("interview-sessions", InterviewSessionViewSet, basename="interview-session")
router.register("interview-scorecards", InterviewScorecardViewSet, basename="interview-scorecard")
router.register("background-checks", BackgroundCheckViewSet, basename="background-check")
# Public, unauthenticated (C6 design spec §3.4) -- kept on its own "careers/"
# prefix so the anonymous surface is visually distinct in the URL space,
# not just in permission_classes.
router.register("careers/postings", PublicPostingViewSet, basename="careers-posting")

urlpatterns = router.urls + [
    path("dashboards/recruitment/", recruitment_dashboard, name="recruitment-dashboard"),
    path("dashboards/recruitment/funnel/", recruitment_funnel_by_demographic, name="recruitment-funnel"),
    path("careers/apply/", careers_apply, name="careers-apply"),
]
