from __future__ import annotations

from rest_framework import permissions, serializers

from .audit import log_access
from .models import AuditLogEntry, Role
from .permissions import active_roles_for, can_access_tier, has_row_access
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


def row_scoped_queryset(queryset, employee, *, employee_field: str = "employee"):
    """Filters a queryset to rows the employee's active roles' row-scope
    permits. Adequate for pilot-scale data (loops employees in Python) —
    Sprint 3's real dashboards should replace this with a set-based query
    (e.g. a recursive CTE for reporting-line membership) at production scale."""
    from core_hr.models import Employee

    if employee is None:
        return queryset.none()

    if any(r.row_scope == Role.RowScope.ALL for r in active_roles_for(employee)):
        return queryset

    accessible_ids = [e.id for e in Employee.objects.all() if has_row_access(employee, e)]
    return queryset.filter(**{f"{employee_field}_id__in": accessible_ids})


class TieredModelSerializer(serializers.ModelSerializer):
    """Drops fields the requesting employee's roles don't have read access
    to, and logs an AuditLogEntry for the highest sensitivity tier
    actually returned. Every module's read serializers for tiered models
    should subclass this instead of building bespoke field filtering."""

    def to_representation(self, instance):
        request = self.context.get("request")
        employee = get_request_employee(request) if request is not None else None
        model_label = f"{self.Meta.model._meta.app_label}.{self.Meta.model._meta.object_name}"

        data = super().to_representation(instance)
        allowed_fields = [
            name
            for name in data
            if tier_of(model_label, name) == FieldTier.PUBLIC
            or can_access_tier(employee, tier_of(model_label, name), mode="read")
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
