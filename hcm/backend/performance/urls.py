from rest_framework.routers import DefaultRouter

from .views import FeedbackViewSet, GoalViewSet, ReviewCycleViewSet, ReviewViewSet
from .views_agreements import (
    AgreementElementViewSet,
    AgreementTemplateViewSet,
    EvidenceItemViewSet,
    ImprovementPlanViewSet,
    PDPItemViewSet,
    PerformanceAgreementViewSet,
    PerformancePeriodViewSet,
    PeriodPhaseViewSet,
    SigningDelegationViewSet,
    TemplateElementViewSet,
    TemplateSectionViewSet,
)
from .views_calibration import CalibrationSessionViewSet
from .views_feedback360 import Feedback360RaterViewSet, Feedback360RequestViewSet

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
# PC-2: portfolio of evidence per KPI x review stage
router.register("agreement-evidence", EvidenceItemViewSet, basename="agreement-evidence")
# PC-3: corrective-action stub behind hr_attention
router.register("improvement-plans", ImprovementPlanViewSet, basename="improvement-plan")
# C6: calibration/moderation + 360 feedback
router.register("calibration-sessions", CalibrationSessionViewSet, basename="calibration-session")
router.register("feedback-360-requests", Feedback360RequestViewSet, basename="feedback-360-request")
router.register("feedback-360-raters", Feedback360RaterViewSet, basename="feedback-360-rater")

urlpatterns = router.urls
