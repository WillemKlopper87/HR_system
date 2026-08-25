"""Service layer for onboarding/offboarding checklists (C1 part 3 slice 3).
Spec: docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md
section 5.

No role/permission checks here -- same 403-vs-400 split core_hr/exits.py's
module docstring argues for: wrong role is a view-layer 403
(onboarding/permissions.py, onboarding/views.py), wrong state is a
ChecklistError -> 400. Every state-changing function is atomic and
audit-logged via rbac_audit's log_access, matching exits.py's own
convention."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from rbac_audit.audit import log_access
from rbac_audit.models import AuditLogEntry
from rbac_audit.tiers import FieldTier

from .models import ChecklistInstance, ChecklistInstanceItem, ChecklistTemplate, ChecklistTemplateItem


class ChecklistError(ValueError):
    """Raised for state-machine violations: publishing an empty or
    already-published template, editing a published template's items,
    creating a second active instance for the same employee+direction, or
    completing an already-complete item."""


def _log(*, actor, entity_type, entity_id, detail) -> None:
    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type=entity_type,
        entity_id=entity_id, field_tier=FieldTier.INTERNAL, fields_touched=detail,
    )


# --- Templates --------------------------------------------------------

@transaction.atomic
def create_template(*, name, direction, actor=None, items=None) -> ChecklistTemplate:
    """Auto-assigns `version` (spec section 4.1): (max version for this
    name+direction) + 1. `items` is an optional list of dicts
    (label/description/owner_role/order) to seed in the same call."""
    next_version = (
        ChecklistTemplate.objects.filter(name=name, direction=direction).aggregate(Max("version"))["version__max"]
        or 0
    ) + 1
    template = ChecklistTemplate.objects.create(
        name=name, direction=direction, version=next_version, created_by=actor,
    )
    for order, item_data in enumerate(items or []):
        data = dict(item_data)
        item_order = data.pop("order", order)
        ChecklistTemplateItem.objects.create(template=template, order=item_order, **data)
    _log(
        actor=actor, entity_type="onboarding.ChecklistTemplate", entity_id=template.id,
        detail=f"created template {name!r} v{next_version} ({direction})",
    )
    return template


@transaction.atomic
def publish_template(template: ChecklistTemplate, *, actor) -> ChecklistTemplate:
    if template.status != ChecklistTemplate.Status.DRAFT:
        raise ChecklistError(f"Cannot publish a template in '{template.status}' state.")
    if not template.items.exists():
        raise ChecklistError("A template needs at least one task before it can be published.")
    template.status = ChecklistTemplate.Status.PUBLISHED
    template.published_at = timezone.now()
    template.save(update_fields=["status", "published_at"])
    _log(
        actor=actor, entity_type="onboarding.ChecklistTemplate", entity_id=template.id,
        detail=f"published template {template.name!r} v{template.version}",
    )
    return template


@transaction.atomic
def retire_template(template: ChecklistTemplate, *, actor) -> ChecklistTemplate:
    if template.status != ChecklistTemplate.Status.PUBLISHED:
        raise ChecklistError(f"Cannot retire a template in '{template.status}' state.")
    template.status = ChecklistTemplate.Status.RETIRED
    template.save(update_fields=["status"])
    _log(
        actor=actor, entity_type="onboarding.ChecklistTemplate", entity_id=template.id,
        detail=f"retired template {template.name!r} v{template.version}",
    )
    return template


def _assert_template_editable(template: ChecklistTemplate) -> None:
    if template.status != ChecklistTemplate.Status.DRAFT:
        raise ChecklistError("Only a draft template's tasks can be edited (spec section 2.4).")


@transaction.atomic
def add_template_item(template: ChecklistTemplate, *, label, description="", owner_role=None, order=None) -> ChecklistTemplateItem:
    _assert_template_editable(template)
    if order is None:
        order = (template.items.aggregate(Max("order"))["order__max"] or 0) + 1
    return ChecklistTemplateItem.objects.create(
        template=template, label=label, description=description,
        owner_role=owner_role or ChecklistTemplateItem.OwnerRole.HR, order=order,
    )


@transaction.atomic
def update_template_item(item: ChecklistTemplateItem, **fields) -> ChecklistTemplateItem:
    _assert_template_editable(item.template)
    for field, value in fields.items():
        setattr(item, field, value)
    item.save()
    return item


@transaction.atomic
def remove_template_item(item: ChecklistTemplateItem) -> None:
    _assert_template_editable(item.template)
    item.delete()


# --- Instances ----------------------------------------------------------

def _assert_no_active_instance(employee, direction) -> None:
    if ChecklistInstance.objects.filter(
        employee=employee, direction=direction, status=ChecklistInstance.Status.ACTIVE
    ).exists():
        raise ChecklistError(
            f"Employee {employee.employee_number} already has an active {direction} checklist."
        )


@transaction.atomic
def create_checklist_instance(employee, template: ChecklistTemplate, *, actor=None, triggering_change=None) -> ChecklistInstance:
    """The one instantiation path every trigger funnels through (spec
    section 5). Copies every template item into a fresh
    ChecklistInstanceItem snapshot (spec section 2.4)."""
    _assert_no_active_instance(employee, template.direction)
    instance = ChecklistInstance.objects.create(
        employee=employee, template=template, template_version=template.version,
        direction=template.direction, created_by=actor, triggering_change=triggering_change,
    )
    ChecklistInstanceItem.objects.bulk_create([
        ChecklistInstanceItem(
            instance=instance, label=item.label, description=item.description,
            owner_role=item.owner_role, order=item.order,
        )
        for item in template.items.all()
    ])
    _log(
        actor=actor, entity_type="onboarding.ChecklistInstance", entity_id=instance.id,
        detail=(
            f"created {template.direction} checklist for {employee.employee_number} "
            f"from template {template.name!r} v{template.version}"
        ),
    )
    return instance


def create_onboarding_checklist_on_hire(employee) -> int:
    """Registered as a lifecycle_hooks hire handler (spec section 6.1, 6.3).
    0 if no onboarding template is published yet -- a hire must never fail
    because a checklist template doesn't exist."""
    template = ChecklistTemplate.current_for(ChecklistTemplate.Direction.ONBOARDING)
    if template is None:
        return 0
    create_checklist_instance(employee, template)
    return 1


def create_offboarding_checklist_on_exit(employee, change) -> int:
    """Registered as a lifecycle_hooks exit-completion handler (spec
    section 6.2, 6.3). Only reached for ENDING change types, by
    construction -- exits.py calls this after apply_lifecycle_event, which
    only runs for ending types."""
    template = ChecklistTemplate.current_for(ChecklistTemplate.Direction.OFFBOARDING)
    if template is None:
        return 0
    create_checklist_instance(employee, template, triggering_change=change)
    return 1


@transaction.atomic
def manually_create_checklist(employee, direction, *, actor, template: ChecklistTemplate | None = None) -> ChecklistInstance:
    """hr_admin fallback trigger (spec section 2.5): a template published
    after the hire/exit already happened, or a checklist that needs
    re-issuing. `template` lets hr_admin pick an explicit version; default
    is the current published one for the direction."""
    if template is None:
        template = ChecklistTemplate.current_for(direction)
        if template is None:
            raise ChecklistError(f"No published {direction} checklist template exists.")
    return create_checklist_instance(employee, template, actor=actor)


# --- Task completion ------------------------------------------------------

@transaction.atomic
def complete_item(item: ChecklistInstanceItem, *, actor, notes: str = "") -> ChecklistInstanceItem:
    if item.is_complete:
        raise ChecklistError("This task is already complete.")
    item.completed_by = actor
    item.completed_at = timezone.now()
    item.notes = notes
    item.save(update_fields=["completed_by", "completed_at", "notes"])
    _log(
        actor=actor, entity_type="onboarding.ChecklistInstanceItem", entity_id=item.id,
        detail=f"completed {item.label!r} on checklist #{item.instance_id}",
    )

    instance = item.instance
    if not instance.items.filter(completed_at__isnull=True).exists():
        instance.status = ChecklistInstance.Status.COMPLETED
        instance.completed_at = timezone.now()
        instance.save(update_fields=["status", "completed_at"])
        _log(
            actor=actor, entity_type="onboarding.ChecklistInstance", entity_id=instance.id,
            detail="all tasks complete, checklist marked completed",
        )
    return item


@transaction.atomic
def reopen_item(item: ChecklistInstanceItem, *, actor) -> ChecklistInstanceItem:
    if not item.is_complete:
        raise ChecklistError("This task is not complete.")
    item.completed_by = None
    item.completed_at = None
    item.notes = ""
    item.save(update_fields=["completed_by", "completed_at", "notes"])
    _log(
        actor=actor, entity_type="onboarding.ChecklistInstanceItem", entity_id=item.id,
        detail=f"reopened {item.label!r} on checklist #{item.instance_id}",
    )

    instance = item.instance
    if instance.status == ChecklistInstance.Status.COMPLETED:
        instance.status = ChecklistInstance.Status.ACTIVE
        instance.completed_at = None
        instance.save(update_fields=["status", "completed_at"])
    return item
