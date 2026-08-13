from rest_framework.routers import DefaultRouter

from .views import BenefitsElectionViewSet, BenefitViewSet, CompProposalViewSet, PayBandViewSet

router = DefaultRouter()
router.register("pay-bands", PayBandViewSet, basename="pay-band")
router.register("comp-proposals", CompProposalViewSet, basename="comp-proposal")
router.register("benefits", BenefitViewSet, basename="benefit")
router.register("benefits-elections", BenefitsElectionViewSet, basename="benefits-election")

urlpatterns = router.urls
