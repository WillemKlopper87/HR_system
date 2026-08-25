"""C1 part 3 slice 3 -- onboarding/offboarding checklist templates and
instances (docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md).
Spec section 8 lists the required tests; this file treats that list as a
floor, not a ceiling -- same convention core_hr/test_exits.py states for
its own spec."""
from __future__ import annotations

from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core_hr.exits import confirm_employment_change, propose_employment_change
from core_hr.models import Department, Employee, EmploymentChange, JobGrade, Location, OccupationalLevel
from rbac_audit.models import Role, RoleAssignment

from .models import ChecklistInstance, ChecklistTemplate, ChecklistTemplateItem
from .services import (
    ChecklistError,
    add_template_item,
    complete_item,
    create_checklist_instance,
    create_offboarding_checklist_on_exit,
    create_onboarding_checklist_on_hire,
    create_template,
    manually_create_checklist,
    publish_template,
    remove_template_item,
    reopen_item,
    retire_template,
    update_template_item,
)


def _seed_reference_data():
    dept = Department.objects.create(name="Operations", code="OPS-CL")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="CL1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="CLHO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ChecklistTestCase(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.dept, self.level, self.grade, self.location = dept, level, grade, location

        self.hr_admin = Employee.objects.hire(
            employee_number="CLHRA1", first_name="HR", last_name="Admin", date_of_birth=date(1980, 1, 1),
            work_email="clhra1@example.com", hire_date=date(2010, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

    def _published_template(self, direction, *, items=None):
        template = create_template(
            name=f"Standard {direction}", direction=direction, actor=self.hr_admin,
            items=items or [
                {"label": "Task one", "owner_role": ChecklistTemplateItem.OwnerRole.HR},
                {"label": "Task two", "owner_role": ChecklistTemplateItem.OwnerRole.LINE_MANAGER},
                {"label": "Task three", "owner_role": ChecklistTemplateItem.OwnerRole.IT},
            ],
        )
        return publish_template(template, actor=self.hr_admin)


class TemplateVersioningTests(ChecklistTestCase):
    def test_creating_a_second_template_with_the_same_name_and_direction_auto_increments_version(self):
        first = create_template(name="Standard onboarding", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        second = create_template(name="Standard onboarding", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)

    def test_a_different_direction_gets_its_own_version_sequence(self):
        onboarding = create_template(name="Shared name", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        offboarding = create_template(name="Shared name", direction=ChecklistTemplate.Direction.OFFBOARDING, actor=self.hr_admin)
        self.assertEqual(onboarding.version, 1)
        self.assertEqual(offboarding.version, 1)

    def test_publishing_an_empty_template_is_rejected(self):
        template = create_template(name="Empty", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        with self.assertRaises(ChecklistError):
            publish_template(template, actor=self.hr_admin)

    def test_publishing_a_non_draft_template_is_rejected(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        with self.assertRaises(ChecklistError):
            publish_template(template, actor=self.hr_admin)

    def test_publishing_v2_does_not_retire_v1(self):
        v1 = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        v2 = create_template(name=v1.name, direction=v1.direction, actor=self.hr_admin, items=[
            {"label": "Only task"},
        ])
        publish_template(v2, actor=self.hr_admin)
        v1.refresh_from_db()
        self.assertEqual(v1.status, ChecklistTemplate.Status.PUBLISHED)
        self.assertEqual(ChecklistTemplate.current_for(v1.direction).version, 2)

    def test_retire_template(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        retire_template(template, actor=self.hr_admin)
        template.refresh_from_db()
        self.assertEqual(template.status, ChecklistTemplate.Status.RETIRED)
        self.assertIsNone(ChecklistTemplate.current_for(template.direction))

    def test_retire_a_non_published_template_is_rejected(self):
        template = create_template(name="Draft only", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        with self.assertRaises(ChecklistError):
            retire_template(template, actor=self.hr_admin)


class TemplateItemEditingTests(ChecklistTestCase):
    def test_items_are_editable_while_draft(self):
        template = create_template(name="Editable", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        item = add_template_item(template, label="Do the thing")
        update_template_item(item, label="Do the updated thing")
        item.refresh_from_db()
        self.assertEqual(item.label, "Do the updated thing")
        remove_template_item(item)
        self.assertEqual(template.items.count(), 0)

    def test_items_are_frozen_once_published(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        item = template.items.first()
        with self.assertRaises(ChecklistError):
            add_template_item(template, label="Too late")
        with self.assertRaises(ChecklistError):
            update_template_item(item, label="Too late")
        with self.assertRaises(ChecklistError):
            remove_template_item(item)


class InstanceCreationTests(ChecklistTestCase):
    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.hire(
            employee_number="CLE001", first_name="New", last_name="Hire", date_of_birth=date(1995, 1, 1),
            work_email="new.hire.cl@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_creating_an_instance_snapshots_every_template_item(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        instance = create_checklist_instance(self.employee, template, actor=self.hr_admin)
        self.assertEqual(instance.items.count(), 3)
        self.assertEqual(instance.template_version, template.version)
        self.assertEqual(instance.direction, template.direction)
        self.assertEqual(instance.status, ChecklistInstance.Status.ACTIVE)

    def test_editing_the_template_after_instantiation_does_not_change_the_instance(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        instance = create_checklist_instance(self.employee, template, actor=self.hr_admin)
        item = instance.items.first()
        original_label = item.label

        v2 = create_template(name=template.name, direction=template.direction, actor=self.hr_admin, items=[
            {"label": "Completely different task"},
        ])
        publish_template(v2, actor=self.hr_admin)

        item.refresh_from_db()
        self.assertEqual(item.label, original_label)

    def test_only_one_active_instance_per_employee_per_direction(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        create_checklist_instance(self.employee, template, actor=self.hr_admin)
        with self.assertRaises(ChecklistError):
            create_checklist_instance(self.employee, template, actor=self.hr_admin)

    def test_the_db_constraint_is_the_real_backstop(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        create_checklist_instance(self.employee, template, actor=self.hr_admin)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ChecklistInstance.objects.create(
                    employee=self.employee, template=template, template_version=template.version,
                    direction=template.direction,
                )

    def test_a_new_instance_is_allowed_once_the_first_is_no_longer_active(self):
        template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        instance = create_checklist_instance(self.employee, template, actor=self.hr_admin)
        instance.status = ChecklistInstance.Status.CANCELLED
        instance.save(update_fields=["status"])
        second = create_checklist_instance(self.employee, template, actor=self.hr_admin)
        self.assertEqual(second.status, ChecklistInstance.Status.ACTIVE)


class HireTriggerTests(ChecklistTestCase):
    def test_hire_creates_an_onboarding_instance_when_a_template_is_published(self):
        self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        employee = Employee.objects.hire(
            employee_number="CLE010", first_name="Auto", last_name="Onboard", date_of_birth=date(1995, 1, 1),
            work_email="auto.onboard@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        instance = ChecklistInstance.objects.get(employee=employee, direction=ChecklistTemplate.Direction.ONBOARDING)
        self.assertEqual(instance.items.count(), 3)
        self.assertIsNone(instance.created_by)
        self.assertIsNone(instance.triggering_change)

    def test_hire_creates_no_instance_when_no_template_is_published(self):
        employee = Employee.objects.hire(
            employee_number="CLE011", first_name="No", last_name="Template", date_of_birth=date(1995, 1, 1),
            work_email="no.template@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.assertFalse(ChecklistInstance.objects.filter(employee=employee).exists())

    def test_backfill_via_manual_create_once_a_template_is_published_later(self):
        employee = Employee.objects.hire(
            employee_number="CLE012", first_name="Late", last_name="Template", date_of_birth=date(1995, 1, 1),
            work_email="late.template@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.assertFalse(ChecklistInstance.objects.filter(employee=employee).exists())
        self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        instance = manually_create_checklist(employee, ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        self.assertEqual(instance.created_by, self.hr_admin)

    def test_manual_create_with_no_published_template_raises(self):
        employee = Employee.objects.hire(
            employee_number="CLE013", first_name="Nope", last_name="Template", date_of_birth=date(1995, 1, 1),
            work_email="nope.template@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        with self.assertRaises(ChecklistError):
            manually_create_checklist(employee, ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)


class ExitTriggerTests(ChecklistTestCase):
    def setUp(self):
        super().setUp()
        self.hr_admin_2 = Employee.objects.hire(
            employee_number="CLHRA2", first_name="Second", last_name="Admin", date_of_birth=date(1981, 1, 1),
            work_email="clhra2@example.com", hire_date=date(2011, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        RoleAssignment.objects.create(employee=self.hr_admin_2, role=Role.objects.get(name="hr_admin"))
        self.employee = Employee.objects.hire(
            employee_number="CLE020", first_name="Departing", last_name="Person", date_of_birth=date(1990, 1, 1),
            work_email="departing.cl@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_an_ending_type_execution_creates_an_offboarding_instance(self):
        self._published_template(ChecklistTemplate.Direction.OFFBOARDING)
        change = propose_employment_change(
            self.employee, actor=self.hr_admin, change_type=EmploymentChange.ChangeType.RESIGNATION,
            effective_date=timezone.localdate(), reason="Moving on.",
        )
        confirm_employment_change(change, actor=self.hr_admin)  # routine type, proposer confirms, executes immediately
        instance = ChecklistInstance.objects.get(employee=self.employee, direction=ChecklistTemplate.Direction.OFFBOARDING)
        self.assertEqual(instance.triggering_change, change)

    def test_a_suspension_execution_creates_no_offboarding_instance(self):
        self._published_template(ChecklistTemplate.Direction.OFFBOARDING)
        change = propose_employment_change(
            self.employee, actor=self.hr_admin, change_type=EmploymentChange.ChangeType.SUSPENSION,
            effective_date=timezone.localdate(), reason="Pending a hearing.",
        )
        confirm_employment_change(change, actor=self.hr_admin_2)  # tiered type, needs a different confirmer
        self.assertFalse(
            ChecklistInstance.objects.filter(employee=self.employee, direction=ChecklistTemplate.Direction.OFFBOARDING).exists()
        )

    def test_a_failing_offboarding_hook_does_not_block_exit_execution(self):
        from core_hr import lifecycle_hooks

        def boom(employee, change):
            raise RuntimeError("checklist hook exploded")

        with lifecycle_hooks.temporary_exit_completion_handler("onboarding.ChecklistInstance", boom):
            change = propose_employment_change(
                self.employee, actor=self.hr_admin, change_type=EmploymentChange.ChangeType.RETIREMENT,
                effective_date=timezone.localdate(), reason="Retiring.",
            )
            confirm_employment_change(change, actor=self.hr_admin)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)


class TaskCompletionTests(ChecklistTestCase):
    def setUp(self):
        super().setUp()
        self.employee = Employee.objects.hire(
            employee_number="CLE030", first_name="Task", last_name="Owner", date_of_birth=date(1995, 1, 1),
            work_email="task.owner@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.template = self._published_template(ChecklistTemplate.Direction.ONBOARDING)
        self.instance = create_checklist_instance(self.employee, self.template, actor=self.hr_admin)

    def test_completing_every_item_marks_the_instance_completed(self):
        for item in self.instance.items.all():
            complete_item(item, actor=self.hr_admin)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, ChecklistInstance.Status.COMPLETED)
        self.assertIsNotNone(self.instance.completed_at)

    def test_completing_some_but_not_all_leaves_the_instance_active(self):
        first = self.instance.items.first()
        complete_item(first, actor=self.hr_admin)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, ChecklistInstance.Status.ACTIVE)

    def test_completing_an_already_complete_item_raises(self):
        item = self.instance.items.first()
        complete_item(item, actor=self.hr_admin)
        with self.assertRaises(ChecklistError):
            complete_item(item, actor=self.hr_admin)

    def test_reopening_an_item_on_a_completed_instance_reverts_it_to_active(self):
        items = list(self.instance.items.all())
        for item in items:
            complete_item(item, actor=self.hr_admin)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, ChecklistInstance.Status.COMPLETED)

        reopen_item(items[0], actor=self.hr_admin)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, ChecklistInstance.Status.ACTIVE)
        self.assertIsNone(self.instance.completed_at)

    def test_reopening_an_incomplete_item_raises(self):
        item = self.instance.items.first()
        with self.assertRaises(ChecklistError):
            reopen_item(item, actor=self.hr_admin)
