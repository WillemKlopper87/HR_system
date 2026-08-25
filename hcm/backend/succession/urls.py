from rest_framework.routers import DefaultRouter

from .views import CriticalPostViewSet, SuccessionCandidateViewSet

router = DefaultRouter()
router.register("critical-posts", CriticalPostViewSet, basename="critical-post")
router.register("succession-candidates", SuccessionCandidateViewSet, basename="succession-candidate")

urlpatterns = router.urls
