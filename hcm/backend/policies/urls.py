from django.urls import path
from rest_framework.routers import DefaultRouter

from .dashboards import acknowledgment_dashboard
from .views import PolicyAcknowledgmentViewSet, PolicyViewSet

router = DefaultRouter()
router.register("policies", PolicyViewSet, basename="policy")
router.register("policy-acknowledgments", PolicyAcknowledgmentViewSet, basename="policy-acknowledgment")

urlpatterns = router.urls + [
    path("dashboards/policy-acknowledgment/", acknowledgment_dashboard, name="policy-acknowledgment-dashboard"),
]
