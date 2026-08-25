"""API for 360 feedback (C6, design spec 2026-08-25-performance-calibration-
360-design.md). No standalone `Feedback360Response` endpoint at all --
responses are only ever created/read through `Feedback360RaterViewSet`'s
`respond` action and the nested `response` field on `Feedback360RaterSerializer`
(masked per §2.10), so there is no second, unmasked read surface to keep in
sync with the masking logic.
"""
from __future__ import annotations

from django.db.models import Q
from rbac_audit.drf import get_request_employee, int_query_param, row_scoped_queryset
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import PerformanceAgreement
from .models.feedback360 import Feedback360Rater, Feedback360Request
from .permissions import (
    Feedback360RaterPermission,
    PerformanceAgreementPermission,
    can_read_all,
    is_admin,
    is_head_of,
)
from .serializers_feedback360 import Feedback360RaterSerializer, Feedback360RequestSerializer, SubmitResponseSerializer
from .services.agreements import AgreementWorkflowError
from .services.feedback360 import (
    approve_rater,
    close_request,
    decline_rater,
    nominate_rater,
    open_request,
    submit_response,
    withdraw_rater,
)
from .views_agreements import _HideForbiddenAsNotFound


def _error(exc: AgreementWorkflowError) -> Response:
    return Response({"detail": str(exc)}, status=409 if getattr(exc, "conflict", False) else 400)


def _visible_agreements(employee):
    return PerformanceAgreement.objects.filter(
        pk__in=row_scoped_queryset(PerformanceAgreement.objects.all(), employee).values("pk")
    ) | PerformanceAgreement.objects.filter(employee=employee)


class Feedback360RequestViewSet(_HideForbiddenAsNotFound, viewsets.ModelViewSet):
    """One 360 round per agreement. Read follows the agreement's own
    audience (`can_view_agreement`); open/close is narrower (subject, Head,
    or hr_admin — enforced explicitly below, same two-layer shape
    `views_agreements.py`'s named actions use)."""

    queryset = Feedback360Request.objects.select_related("agreement__employee", "agreement__head", "opened_by").prefetch_related(
        "raters__rater", "raters__response"
    )
    serializer_class = Feedback360RequestSerializer
    permission_classes = [PerformanceAgreementPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        agreement_id = int_query_param(self.request, "agreement")
        if agreement_id is not None:
            qs = qs.filter(agreement_id=agreement_id)
        if can_read_all(employee):
            return qs
        if self.action != "list":
            return qs  # object permission decides; see PerformanceAgreementViewSet.get_queryset
        return qs.filter(agreement__in=_visible_agreements(employee).distinct())

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj.agreement)

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        agreement = serializer.validated_data["agreement"]
        if not (is_head_of(agreement, actor) or is_admin(actor) or agreement.employee_id == actor.pk):
            raise PermissionError("open")
        feedback_request = open_request(agreement, actor=actor, due_date=serializer.validated_data.get("due_date"))
        serializer.instance = feedback_request

    def handle_exception(self, exc):
        if isinstance(exc, PermissionError):
            return Response(
                {"detail": "Only the employee, their Head, or hr_admin can open a 360 round."}, status=403
            )
        if isinstance(exc, AgreementWorkflowError):
            return _error(exc)
        return super().handle_exception(exc)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        feedback_request = self.get_object()
        actor = get_request_employee(request)
        agreement = feedback_request.agreement
        if not (is_head_of(agreement, actor) or is_admin(actor)):
            return Response({"detail": "Only the Head or hr_admin can close a 360 round."}, status=403)
        try:
            close_request(feedback_request, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        feedback_request.refresh_from_db()
        return Response(self.get_serializer(feedback_request).data)


class Feedback360RaterViewSet(_HideForbiddenAsNotFound, viewsets.ModelViewSet):
    """Rater slots: nomination, approval, response. See
    `Feedback360RaterPermission` for the two-layer authority split."""

    queryset = Feedback360Rater.objects.select_related(
        "request__agreement__employee", "request__agreement__head", "request__agreement__period",
        "rater", "nominated_by", "approved_by", "response",
    )
    serializer_class = Feedback360RaterSerializer
    permission_classes = [Feedback360RaterPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        request_id = int_query_param(self.request, "request")
        if request_id is not None:
            qs = qs.filter(request_id=request_id)
        # ?mine=true forces "slots I'm personally the rater for", even for
        # hr_admin/auditor -- same shape recruitment's InterviewSession
        # `?mine=true` uses, for the identical reason: "give me the admin
        # view of every round" and "give me only what I've been asked to
        # rate" are different requests role alone can't distinguish.
        if self.request.query_params.get("mine") == "true":
            return qs.filter(rater=employee)
        if can_read_all(employee):
            return qs
        if self.action != "list":
            return qs  # object permission decides
        # A rater's own slots are reachable even when they have no other
        # access to the agreement (a plain peer/direct-report usually can't
        # view the agreement itself) -- union, not just the visible-agreement
        # scope PerformanceAgreementViewSet's list uses.
        visible = _visible_agreements(employee)
        return qs.filter(Q(request__agreement__in=visible.distinct()) | Q(rater=employee)).distinct()

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        feedback_request = serializer.validated_data["request"]
        candidate = serializer.validated_data["rater"]
        agreement = feedback_request.agreement
        if not (is_head_of(agreement, actor) or is_admin(actor) or agreement.employee_id == actor.pk):
            raise PermissionError("nominate")
        rater_slot = nominate_rater(feedback_request, candidate, actor=actor)
        serializer.instance = rater_slot

    def handle_exception(self, exc):
        if isinstance(exc, PermissionError):
            return Response(
                {"detail": "Only the employee, their Head, or hr_admin can nominate a rater."}, status=403
            )
        if isinstance(exc, AgreementWorkflowError):
            return _error(exc)
        return super().handle_exception(exc)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        slot = self.get_object()
        actor = get_request_employee(request)
        agreement = slot.request.agreement
        if not (is_head_of(agreement, actor) or is_admin(actor)):
            return Response({"detail": "Only the Head or hr_admin can approve a nomination."}, status=403)
        try:
            approve_rater(slot, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        slot.refresh_from_db()
        return Response(self.get_serializer(slot).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        slot = self.get_object()
        actor = get_request_employee(request)
        agreement = slot.request.agreement
        if not (is_head_of(agreement, actor) or is_admin(actor)):
            return Response({"detail": "Only the Head or hr_admin can decline a nomination."}, status=403)
        try:
            decline_rater(slot, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        slot.refresh_from_db()
        return Response(self.get_serializer(slot).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        slot = self.get_object()
        actor = get_request_employee(request)
        agreement = slot.request.agreement
        if not (is_head_of(agreement, actor) or is_admin(actor) or actor.pk == slot.rater_id):
            return Response({"detail": "You cannot withdraw this rater."}, status=403)
        try:
            withdraw_rater(slot, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        slot.refresh_from_db()
        return Response(self.get_serializer(slot).data)

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        slot = self.get_object()
        actor = get_request_employee(request)
        if actor.pk != slot.rater_id:
            return Response({"detail": "Only the named rater can submit this response."}, status=403)
        payload = SubmitResponseSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            submit_response(slot, actor=actor, **payload.validated_data)
        except AgreementWorkflowError as exc:
            return _error(exc)
        slot.refresh_from_db()
        return Response(self.get_serializer(slot).data)
