from __future__ import annotations

import os

from django.http import FileResponse
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Policy, PolicyAcknowledgment
from .permissions import IsHRAdminOrReadOnly, IsSelfOrHRAdmin
from .serializers import PolicyAcknowledgmentSerializer, PolicyChunkSerializer, PolicySerializer
from .services import (
    PolicyWorkflowError,
    acknowledge_policy,
    archive_policy,
    create_new_version,
    create_policy,
    publish_policy,
    update_draft,
)


class PolicyViewSet(viewsets.ModelViewSet):
    """No DELETE — a policy leaves circulation via the archive action, not
    row deletion, so acknowledgments always stay attached to something
    real (PROTECT on PolicyAcknowledgment.policy already enforces this at
    the DB layer; http_method_names keeps the API surface honest about it)."""

    queryset = Policy.objects.select_related("created_by", "published_by")
    serializer_class = PolicySerializer
    permission_classes = [IsHRAdminOrReadOnly]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None or not has_role(employee, "hr_admin"):
            # Draft/archived policies aren't just "hr_admin write, everyone
            # read" — a plain employee has no business seeing an
            # in-progress or retired policy at all, including via direct
            # detail/chunks lookup (both route through this queryset), so
            # this overrides whatever ?status= the client asked for rather
            # than trusting it. A 404 here (not 403) is deliberate: the
            # existence of an unpublished policy isn't information a
            # non-hr_admin should have confirmed to them either.
            queryset = queryset.filter(status=Policy.Status.PUBLISHED)
        else:
            status_param = self.request.query_params.get("status")
            if status_param:
                queryset = queryset.filter(status=status_param)
        code = self.request.query_params.get("code")
        if code:
            queryset = queryset.filter(code=code)
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.instance = create_policy(
                title=serializer.validated_data["title"],
                category=serializer.validated_data.get("category", Policy.Category.OTHER),
                body=serializer.validated_data.get("body", ""),
                file=serializer.validated_data.get("source_file"),
                effective_date=serializer.validated_data.get("effective_date"),
                actor=get_request_employee(self.request),
            )
        except PolicyWorkflowError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def perform_update(self, serializer):
        data = serializer.validated_data
        try:
            serializer.instance = update_draft(
                serializer.instance,
                title=data.get("title"),
                category=data.get("category"),
                body=data.get("body"),
                file=data.get("source_file"),
                effective_date=data.get("effective_date"),
            )
        except PolicyWorkflowError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"])
    def new_version(self, request, pk=None):
        policy = self.get_object()
        try:
            new_policy = create_new_version(
                policy,
                title=request.data.get("title"),
                category=request.data.get("category"),
                body=request.data.get("body"),
                file=request.data.get("source_file"),
                effective_date=request.data.get("effective_date"),
                actor=get_request_employee(request),
            )
        except PolicyWorkflowError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(new_policy).data, status=201)

    @action(detail=True, methods=["get"])
    def chunks(self, request, pk=None):
        """Read-only inspection of the retrieval passages generated from
        this policy's body — useful for QA'ing extraction/chunking now,
        and the same data a future chatbot phase would embed and search
        over (no embeddings exist yet; see the model docstring)."""
        policy = self.get_object()
        return Response(PolicyChunkSerializer(policy.chunks.all(), many=True).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """The authenticated route to the original uploaded document —
        `self.get_object()` runs the same permission + status-filtered
        queryset as every other action, unlike a raw MEDIA_URL link (which
        `django.views.static.serve` would hand out to anyone, logged in or
        not, if it were still mounted). See PolicySerializer.download_url."""
        policy = self.get_object()
        if not policy.source_file:
            return Response({"detail": "This policy has no uploaded source document."}, status=404)
        filename = os.path.basename(policy.source_file.name)
        return FileResponse(policy.source_file.open("rb"), as_attachment=True, filename=filename)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        policy = self.get_object()
        try:
            publish_policy(policy, actor=get_request_employee(request))
        except PolicyWorkflowError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(policy).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        policy = self.get_object()
        try:
            archive_policy(policy, actor=get_request_employee(request))
        except PolicyWorkflowError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(policy).data)


class PolicyAcknowledgmentViewSet(viewsets.ModelViewSet):
    """No PATCH/DELETE — an attestation is immutable once made; re-reading
    the same policy and acknowledging again is just idempotent (see
    services.py::acknowledge_policy), not an edit."""

    queryset = PolicyAcknowledgment.objects.select_related("employee", "policy")
    serializer_class = PolicyAcknowledgmentSerializer
    permission_classes = [IsSelfOrHRAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            # Detail lookups must NOT be row-scope-filtered here — same
            # reasoning as core_hr.EmployeeVersionViewSet.get_queryset():
            # let IsSelfOrHRAdmin's object check produce the 403.
            return queryset
        employee = get_request_employee(self.request)
        if employee is not None and has_role(employee, "hr_admin"):
            return queryset
        return queryset.filter(employee=employee)

    def perform_create(self, serializer):
        # Always self — see the model/serializer docstrings for why an
        # hr_admin-on-behalf-of path doesn't exist here, unlike
        # compensation.BenefitsElection.
        employee = get_request_employee(self.request)
        policy = serializer.validated_data["policy"]
        try:
            serializer.instance = acknowledge_policy(policy, employee=employee)
        except PolicyWorkflowError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
