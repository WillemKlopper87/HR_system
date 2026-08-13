from rest_framework.routers import DefaultRouter

from .views import AssessmentAssignmentViewSet, ProviderConfigViewSet

router = DefaultRouter()
router.register("assessment-assignments", AssessmentAssignmentViewSet, basename="assessment-assignment")
router.register("provider-configs", ProviderConfigViewSet, basename="provider-config")

urlpatterns = router.urls
