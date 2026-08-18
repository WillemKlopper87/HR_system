from rest_framework.routers import DefaultRouter

from .views import FeedbackViewSet, GoalViewSet, ReviewCycleViewSet, ReviewViewSet
from .views_agreements import (
    AgreementElementViewSet,
    AgreementTemplateViewSet,
    PDPItemViewSet,
    PerformanceAgreementViewSet,
    PerformancePeriodViewSet,
    PeriodPhaseViewSet,
    SigningDelegationViewSet,
    TemplateElementViewSet,
    TemplateSectionViewSet,
)

router = DefaultRouter()
router.register("review-cycles", ReviewCycleViewSet, basename="review-cycle")
router.register("goals", GoalViewSet, basename="goal")
router.register("reviews", ReviewViewSet, basename="review")
router.register("feedback", FeedbackViewSet, basename="feedback")

# Performance agreements / KPI contracting (PC-1, ADR-010)
router.register("performance-periods", PerformancePeriodViewSet, basename="performance-period")
router.register("performance-phases", PeriodPhaseViewSet, basename="performance-phase")
router.register("agreement-templates", AgreementTemplateViewSet, basename="agreement-template")
router.register("agreement-template-sections", TemplateSectionViewSet, basename="agreement-template-section")
router.register("agreement-template-elements", TemplateElementViewSet, basename="agreement-template-element")
router.register("performance-agreements", PerformanceAgreementViewSet, basename="performance-agreement")
router.register("agreement-elements", AgreementElementViewSet, basename="agreement-element")
router.register("agreement-pdp-items", PDPItemViewSet, basename="agreement-pdp-item")
router.register("signing-delegations", SigningDelegationViewSet, basename="signing-delegation")

urlpatterns = router.urls
