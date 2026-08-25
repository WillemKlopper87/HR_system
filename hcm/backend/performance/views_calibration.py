"""API for calibration/moderation (C6, design spec 2026-08-25-performance-
calibration-360-design.md). Every write goes through services/calibration.py
so the audit trail (guardrail: no silent overwrite) is never bypassable via
a raw PATCH -- `CalibrationSession.status` and every `CalibrationAdjustment`
field are read-only on their serializers.
"""
from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import PerformanceAgreement
from .models.calibration import CalibrationSession
from .permissions import CalibrationSessionPermission
from .serializers_calibration import (
    CalibrationCandidateSerializer,
    CalibrationSessionSerializer,
    RecordOutcomeSerializer,
)
from .services.agreements import AgreementWorkflowError
from .services.calibration import close_session, eligible_agreements, open_session, record_calibration_outcome


def _error(exc: AgreementWorkflowError) -> Response:
    return Response({"detail": str(exc)}, status=409 if getattr(exc, "conflict", False) else 400)


class CalibrationSessionViewSet(viewsets.ModelViewSet):
    queryset = CalibrationSession.objects.select_related("period", "department", "convened_by").prefetch_related(
        "adjustments__agreement__employee", "adjustments__adjusted_by"
    )
    serializer_class = CalibrationSessionSerializer
    permission_classes = [CalibrationSessionPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        period_id = self.request.query_params.get("period")
        if period_id:
            qs = qs.filter(period_id=period_id)
        return qs

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        session = open_session(
            period=serializer.validated_data["period"],
            department=serializer.validated_data.get("department"),
            actor=actor,
            meeting_date=serializer.validated_data.get("meeting_date"),
            participants_note=serializer.validated_data.get("participants_note", ""),
        )
        serializer.instance = session

    @action(detail=True, methods=["get"])
    def candidates(self, request, pk=None):
        """Eligible cohort not yet recorded in this session — what the
        hr_admin picks from when recording outcomes."""
        session = self.get_object()
        already = set(session.adjustments.values_list("agreement_id", flat=True))
        agreements = [a for a in eligible_agreements(session) if a.id not in already]
        return Response(CalibrationCandidateSerializer(agreements, many=True).data)

    @action(detail=True, methods=["post"], url_path="record-outcome")
    def record_outcome(self, request, pk=None):
        session = self.get_object()
        payload = RecordOutcomeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            agreement = PerformanceAgreement.objects.get(pk=payload.validated_data["agreement"])
        except PerformanceAgreement.DoesNotExist:
            return Response({"detail": "That agreement does not exist."}, status=400)
        try:
            adjustment = record_calibration_outcome(
                session, agreement, actor=get_request_employee(request),
                reason=payload.validated_data["reason"], new_score=payload.validated_data.get("new_score"),
            )
        except AgreementWorkflowError as exc:
            return _error(exc)
        session.refresh_from_db()
        return Response(self.get_serializer(session).data, status=201)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        session = self.get_object()
        try:
            close_session(session, actor=get_request_employee(request))
        except AgreementWorkflowError as exc:
            return _error(exc)
        session.refresh_from_db()
        return Response(self.get_serializer(session).data)
