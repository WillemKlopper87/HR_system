from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ApplicantViewSet, OfferViewSet, RequisitionViewSet, recruitment_dashboard

router = DefaultRouter()
router.register("requisitions", RequisitionViewSet, basename="requisition")
router.register("applicants", ApplicantViewSet, basename="applicant")
router.register("offers", OfferViewSet, basename="offer")

urlpatterns = router.urls + [
    path("dashboards/recruitment/", recruitment_dashboard, name="recruitment-dashboard"),
]
