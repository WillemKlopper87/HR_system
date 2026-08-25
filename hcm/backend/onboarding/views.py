from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.permissions import has_role, is_in_reporting_chain

from .models import ChecklistInstance, ChecklistInstanceItem, ChecklistTemplate, ChecklistTemplateItem
from .permissions import ChecklistInstancePermission, ChecklistTemplatePermission
from .serializers import (
    ChecklistInstanceItemSerializer,
    ChecklistInstanceSerializer,
    ChecklistTemplateItemSerializer,
    ChecklistTemplateSerializer,
)
from .services import (
    ChecklistError,
    add_template_item,
    complete_item,
    create_template,
    manually_create_checklist,
    publish_template,
    reopen_item,
    retire_template,
    update_template_item,
)


def _error(exc: ChecklistError) -> Response:
    return Response({"detail": str(exc)}, status=400)


class ChecklistTemplateViewSet(viewsets.ModelViewSet):
    """Template CRUD + publish/retire (design spec section 5, 7). No
    PATCH/PUT on the template row itself beyond what ModelViewSet gives for
    free -- name/direction rarely change after creation, and version/status
    are always service-driven (ChecklistTemplateSerializer's read-only
    fields)."""

    queryset = ChecklistTemplate.objects.prefetch_related("items").all()
    serializer_class = ChecklistTemplateSerializer
    permission_classes = [ChecklistTemplatePermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        direction = self.request.query_params.get("direction")
        if direction:
            queryset = queryset.filter(direction=direction)
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.instance = create_template(
                name=serializer.validated_data["name"],
                direction=serializer.validated_data["direction"],
                actor=get_request_employee(self.request),
            )
        except ChecklistError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        try:
            template = publish_template(self.get_object(), actor=get_request_employee(request))
        except ChecklistError as exc:
            return _error(exc)
        return Response(self.get_serializer(template).data)

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        try:
            template = retire_template(self.get_object(), actor=get_request_employee(request))
        except ChecklistError as exc:
            return _error(exc)
        return Response(self.get_serializer(template).data)


class ChecklistTemplateItemViewSet(viewsets.ModelViewSet):
    """Flat ordered task list per template (design spec section 2.3 -- no
    section grouping, deliberately simpler than performance's
    TemplateElement/TemplateSection pair). Every write routes through
    services.py so 'only a draft template's tasks can be edited' (spec
    section 2.4) is enforced in one place rather than repeated per action."""

    queryset = ChecklistTemplateItem.objects.select_related("template").all()
    serializer_class = ChecklistTemplateItemSerializer
    permission_classes = [ChecklistTemplatePermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        template_id = int_query_param(self.request, "template")
        if template_id is not None:
            queryset = queryset.filter(template_id=template_id)
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.instance = add_template_item(
                serializer.validated_data["template"],
                label=serializer.validated_data["label"],
                description=serializer.validated_data.get("description", ""),
                owner_role=serializer.validated_data.get("owner_role"),
                order=serializer.validated_data.get("order"),
            )
        except ChecklistError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def perform_update(self, serializer):
        try:
            update_template_item(serializer.instance, **serializer.validated_data)
        except ChecklistError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def perform_destroy(self, instance):
        try:
            if instance.template.status != ChecklistTemplate.Status.DRAFT:
                raise ChecklistError("Only a draft template's tasks can be edited (spec section 2.4).")
            instance.delete()
        except ChecklistError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class ChecklistInstanceViewSet(viewsets.ModelViewSet):
    """The employee-facing side (design spec section 5, 7). No PATCH/PUT/
    DELETE -- an instance only ever moves via task completion
    (ChecklistInstanceItemViewSet, below) or the automatic hire/exit hooks;
    the one write here is a manual hr_admin create (spec section 2.5's
    backfill path).

    Row visibility (get_queryset, not a blanket permission class -- same
    split EmployeeVersion's nested contract_renewal_decision read gate
    uses): hr_admin/auditor see everything; a line_manager sees their
    reporting chain (RBAC-Roles.md's own_team scope, via
    is_in_reporting_chain); anyone else sees only their own record."""

    queryset = ChecklistInstance.objects.select_related(
        "employee", "template", "triggering_change", "created_by"
    ).prefetch_related("items")
    serializer_class = ChecklistInstanceSerializer
    permission_classes = [ChecklistInstancePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        direction = self.request.query_params.get("direction")
        if direction:
            queryset = queryset.filter(direction=direction)
        employee_id = int_query_param(self.request, "employee")
        if employee_id is not None:
            queryset = queryset.filter(employee_id=employee_id)

        actor = get_request_employee(self.request)
        if has_role(actor, "hr_admin") or has_role(actor, "auditor"):
            return queryset.order_by("-created_at")
        visible_ids = [
            row.id for row in queryset
            if row.employee_id == actor.id
            or (has_role(actor, "line_manager") and is_in_reporting_chain(actor, row.employee))
        ]
        return queryset.filter(id__in=visible_ids).order_by("-created_at")

    def perform_create(self, serializer):
        try:
            serializer.instance = manually_create_checklist(
                serializer.validated_data["employee"],
                serializer.validated_data["direction"],
                actor=get_request_employee(self.request),
                template=serializer.validated_data.get("template"),
            )
        except ChecklistError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class ChecklistInstanceItemViewSet(viewsets.ModelViewSet):
    """Task completion (design spec section 5, 7 -- decision 1). Read-only
    on the row itself (ChecklistInstanceItemSerializer's read_only_fields);
    every state change goes through the complete/reopen actions, which are
    where the owner_role + reporting-chain gate actually lives -- like
    exits.py's tiered-confirm rule, that decision needs the specific row's
    data, not just the actor's role, so it can't be a blanket permission
    class."""

    queryset = ChecklistInstanceItem.objects.select_related(
        "instance", "instance__employee", "completed_by"
    ).all()
    serializer_class = ChecklistInstanceItemSerializer
    permission_classes = [ChecklistInstancePermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        instance_id = int_query_param(self.request, "instance")
        if instance_id is not None:
            queryset = queryset.filter(instance_id=instance_id)

        actor = get_request_employee(self.request)
        if has_role(actor, "hr_admin") or has_role(actor, "auditor"):
            return queryset.order_by("instance", "order", "id")
        visible_ids = [
            row.id for row in queryset
            if row.instance.employee_id == actor.id
            or (has_role(actor, "line_manager") and is_in_reporting_chain(actor, row.instance.employee))
        ]
        return queryset.filter(id__in=visible_ids).order_by("instance", "order", "id")

    def _can_complete(self, actor, item: ChecklistInstanceItem) -> bool:
        """Design spec section 3 decision 1: hr_admin always; a
        line_manager only for a task explicitly owned by line_manager, only
        in their own reporting chain; nobody else -- an employee can see
        their own checklist (get_queryset above) but never marks a row
        done themselves."""
        if has_role(actor, "hr_admin"):
            return True
        return (
            has_role(actor, "line_manager")
            and item.owner_role == ChecklistTemplateItem.OwnerRole.LINE_MANAGER
            and is_in_reporting_chain(actor, item.instance.employee)
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        item = self.get_object()
        actor = get_request_employee(request)
        if not self._can_complete(actor, item):
            return Response({"detail": "You may not complete this task."}, status=403)
        try:
            complete_item(item, actor=actor, notes=request.data.get("notes", ""))
        except ChecklistError as exc:
            return _error(exc)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        item = self.get_object()
        actor = get_request_employee(request)
        if not self._can_complete(actor, item):
            return Response({"detail": "You may not reopen this task."}, status=403)
        try:
            reopen_item(item, actor=actor)
        except ChecklistError as exc:
            return _error(exc)
        return Response(self.get_serializer(item).data)
