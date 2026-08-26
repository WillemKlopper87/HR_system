from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BenefitsElectionViewSet,
    BenefitViewSet,
    CompCycleViewSet,
    CompProposalViewSet,
    PayBandViewSet,
    my_total_rewards_statement,
)

router = DefaultRouter()
router.register("pay-bands", PayBandViewSet, basename="pay-band")
router.register("comp-cycles", CompCycleViewSet, basename="comp-cycle")
router.register("comp-proposals", CompProposalViewSet, basename="comp-proposal")
router.register("benefits", BenefitViewSet, basename="benefit")
router.register("benefits-elections", BenefitsElectionViewSet, basename="benefits-election")

urlpatterns = router.urls + [
    path("my-total-rewards/", my_total_rewards_statement, name="my-total-rewards"),
]
