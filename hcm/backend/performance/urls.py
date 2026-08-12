from rest_framework.routers import DefaultRouter

from .views import FeedbackViewSet, GoalViewSet, ReviewCycleViewSet, ReviewViewSet

router = DefaultRouter()
router.register("review-cycles", ReviewCycleViewSet, basename="review-cycle")
router.register("goals", GoalViewSet, basename="goal")
router.register("reviews", ReviewViewSet, basename="review")
router.register("feedback", FeedbackViewSet, basename="feedback")

urlpatterns = router.urls
