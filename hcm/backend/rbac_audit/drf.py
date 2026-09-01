from __future__ import annotations

from rest_framework import permissions, serializers

from .audit import log_access
from .models import AuditLogEntry
from .permissions import accessible_employee_ids, can_access_tier_for_target, has_row_access
from .tiers import FieldTier, highest_tier, tier_of


def get_request_employee(request):
    """Resolves request.user to their core_hr Employee record. DRF
    resolves authentication (session, force_authenticate in tests, or a
    future OIDC token per ADR-004) inside view dispatch — after Django's
    own middleware chain has already run — so this is looked up here
    rather than attached by a middleware, which would see a stale
    request.user at the point it ran."""
    from core_hr.models import Employee

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return Employee.objects.filter(user=user).first()


def int_query_param(request, name: str) -> int | None:
    """Safely parses a query param used as a DB id filter (e.g. ?employee=).
    Returns None if absent or not a valid integer — every module's
    get_queryset() should route these through here rather than passing the
    raw string straight to .filter(field_id=value): an invalid value (e.g.
    "1' OR '1'='1" or "10-2") reaching the ORM unvalidated raises an
    unhandled ValueError, producing a 500 with Django's DEBUG traceback
    page exposed rather than a clean, filter-ignored response."""
    value = request.query_params.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class RowScopePermission(permissions.IsAuthenticated):
    """Object-level row-scope (all/own_team/self) enforcement. Blocks — and
    logs (Sprint 2 acceptance criterion) — access to a record outside the
    requester's scope. Every module's protected viewsets should use this
    instead of building bespoke access control (sprint plan hard rule).

    Viewsets using this must implement get_target_employee(obj)."""

    def has_object_permission(self, request, view, obj):
        employee = get_request_employee(request)
        target_employee = view.get_target_employee(obj)
        model_label = f"{obj._meta.app_label}.{obj._meta.object_name}"

        if has_row_access(employee, target_employee):
            return True

        log_access(
            actor=employee,
            action=AuditLogEntry.Action.ACCESS_DENIED,
            entity_type=model_label,
            entity_id=obj.pk,
            field_tier=FieldTier.RESTRICTED,
            fields_touched="<row scope>",
        )
        return False


def row_scoped_queryset(queryset, employee, *, employee_field: str | None = "employee"):
    """Filters a queryset to rows the employee's active roles' row-scope
    permits. `employee_field=None` means the row itself IS the employee
    (e.g. the Employee model's own queryset) rather than a queryset with a
    foreign key to one. Reporting chains are expanded with set-based queries
    per hierarchy level, so unrelated workforce size does not increase query
    count or require loading Employee objects in Python."""
    accessible_ids = accessible_employee_ids(employee)
    if accessible_ids is None:
        return queryset
    lookup = "pk__in" if employee_field is None else f"{employee_field}_id__in"
    return queryset.filter(**{lookup: accessible_ids})


class TieredModelSerializer(serializers.ModelSerializer):
    """Drops fields the requesting employee's roles don't have read access
    to *for this specific record*, and logs an AuditLogEntry for the
    highest sensitivity tier actually returned. Every module's read
    serializers for tiered models should subclass this instead of building
    bespoke field filtering.

    Requires the viewset to implement get_target_employee(obj) — the same
    method RowScopePermission already requires — so a role's tier grant
    only applies within that role's own row-scope (can_access_tier_for_target),
    not "this employee holds a matching grant via any role, for any record."""

    def to_representation(self, instance):
        request = self.context.get("request")
        view = self.context.get("view")
        employee = get_request_employee(request) if request is not None else None
        target_employee = view.get_target_employee(instance) if view is not None else None
        model_label = f"{self.Meta.model._meta.app_label}.{self.Meta.model._meta.object_name}"

        data = super().to_representation(instance)
        allowed_fields = [
            name
            for name in data
            if tier_of(model_label, name) == FieldTier.PUBLIC
            or can_access_tier_for_target(employee, target_employee, tier_of(model_label, name), mode="read")
        ]
        filtered = {name: data[name] for name in allowed_fields}

        touched_tier = highest_tier(model_label, allowed_fields)
        if touched_tier != FieldTier.PUBLIC:
            log_access(
                actor=employee,
                action=AuditLogEntry.Action.READ_SENSITIVE,
                entity_type=model_label,
                entity_id=instance.pk,
                field_tier=touched_tier,
                fields_touched=",".join(allowed_fields),
            )
        return filtered
