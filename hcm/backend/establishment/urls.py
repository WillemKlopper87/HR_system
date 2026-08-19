# hcm/backend/establishment/urls.py
from rest_framework.routers import DefaultRouter

from .views import PositionViewSet

router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")

urlpatterns = router.urls
