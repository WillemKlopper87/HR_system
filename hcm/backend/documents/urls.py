from rest_framework.routers import DefaultRouter

from .views import DataSubjectRequestViewSet, EmployeeDocumentViewSet

router = DefaultRouter()
router.register("employee-documents", EmployeeDocumentViewSet, basename="employee-document")
router.register("data-subject-requests", DataSubjectRequestViewSet, basename="data-subject-request")

urlpatterns = router.urls
