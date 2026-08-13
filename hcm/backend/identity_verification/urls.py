from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BiometricEnrollmentViewSet, LivenessCheckViewSet, attendance_summary

router = DefaultRouter()
router.register("biometric-enrollments", BiometricEnrollmentViewSet, basename="biometric-enrollment")
router.register("liveness-checks", LivenessCheckViewSet, basename="liveness-check")

urlpatterns = router.urls + [
    path("dashboards/attendance/", attendance_summary, name="attendance-summary"),
]
