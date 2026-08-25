from rest_framework.routers import DefaultRouter

from .views import (
    ChecklistInstanceItemViewSet,
    ChecklistInstanceViewSet,
    ChecklistTemplateItemViewSet,
    ChecklistTemplateViewSet,
)

router = DefaultRouter()
router.register("checklist-templates", ChecklistTemplateViewSet, basename="checklist-template")
router.register("checklist-template-items", ChecklistTemplateItemViewSet, basename="checklist-template-item")
router.register("checklist-instances", ChecklistInstanceViewSet, basename="checklist-instance")
router.register("checklist-items", ChecklistInstanceItemViewSet, basename="checklist-item")

urlpatterns = router.urls
