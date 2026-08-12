from rest_framework.routers import DefaultRouter

from .views import EmployeeVersionViewSet

router = DefaultRouter()
router.register("employee-versions", EmployeeVersionViewSet, basename="employee-version")

urlpatterns = router.urls
