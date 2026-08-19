# hcm/backend/establishment/views.py
from __future__ import annotations

from django.conf import settings
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Position
from .permissions import EstablishmentPermission
from .serializers import PositionSerializer
from .services import ApprovalError, decide_step, propose_position, revise_and_resubmit, submit_for_approval


def _require_hr_admin(actor, message):
    if not has_role(actor, "hr_admin"):
        raise PermissionDenied(message)


class PositionViewSet(viewsets.ModelViewSet):
    """No direct create/update via a raw PATCH of status/current_step --
    those are state-machine-managed (services.py); this viewset's create()
    IS allowed (it's just propose_position with role validation), but
    submit/decide/revise are separate named actions, matching
    ee_reporting.views.EEReportViewSet's own reasoning."""

    queryset = Position.objects.select_related(
        "department", "occupational_level", "job_grade", "location", "proposed_by"
    ).prefetch_related("approval_steps")
    serializer_class = PositionSerializer
    permission_classes = [EstablishmentPermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        privileged = ("hr_admin", "comp_manager", "accounting_officer", "auditor")
        if employee is not None and not any(has_role(employee, r) for r in privileged):
            # recruiter (or anyone else with only read access) sees approved
            # positions only -- not the approval-chain detail of in-review ones.
            qs = qs.filter(status=Position.Status.APPROVED)
        vacant_only = self.request.query_params.get("vacant") == "true"
        if vacant_only:
            qs = qs.filter(id__in=Position.objects.vacant().values("id"))
        return qs

    def create(self, request, *args, **kwargs):
        actor = get_request_employee(request)
        _require_hr_admin(actor, "Only hr_admin can propose a position.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # job_grade is optional (Position.job_grade is null=True/blank=True,
        # so the serializer's is_valid() doesn't require it) but
        # propose_position()'s job_grade parameter has no default -- omitting
        # it from request.data would otherwise omit the key entirely from
        # this spread and crash propose_position() with a TypeError.
        validated = dict(serializer.validated_data)
        validated.setdefault("job_grade", None)
        position = propose_position(actor=actor, **validated)
        return Response(self.get_serializer(position).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        actor = get_request_employee(request)
        _require_hr_admin(actor, "Only hr_admin can submit a position for approval.")
        position = self.get_object()
        try:
            submit_for_approval(position, actor=actor)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(position).data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        position = self.get_object()
        actor = get_request_employee(request)
        chain = settings.POSITION_APPROVAL_CHAIN
        if position.current_step < len(chain):
            required_role = chain[position.current_step]
            if not has_role(actor, required_role):
                raise PermissionDenied(f"Only {required_role} can decide this step.")
        decision = request.data.get("decision")
        try:
            decide_step(position, actor=actor, decision=decision, comment=request.data.get("comment", ""))
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(position).data)

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        actor = get_request_employee(request)
        _require_hr_admin(actor, "Only hr_admin can revise a rejected position.")
        position = self.get_object()
        allowed_fields = {"title", "department", "occupational_level", "job_grade", "location"}
        # Route through the serializer (partial=True: only fields present in
        # request.data are validated/returned) rather than passing
        # request.data straight through -- FK fields arrive as raw ids over
        # JSON, and revise_and_resubmit's setattr(position, field, value)
        # requires a resolved model instance; PrimaryKeyRelatedField.
        # to_internal_value() does that resolution (and raises a clean 400
        # via is_valid(raise_exception=True) for an unknown id) instead of
        # setattr crashing with an unhandled ValueError.
        serializer = self.get_serializer(instance=position, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changed = {k: v for k, v in serializer.validated_data.items() if k in allowed_fields}
        try:
            revise_and_resubmit(position, actor=actor, **changed)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(position).data)
