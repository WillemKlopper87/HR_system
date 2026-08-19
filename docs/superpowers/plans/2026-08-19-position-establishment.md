# Position / Establishment Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Sentech a real notion of an approved establishment post (`Position`) — approved-vs-filled visibility,
post-numbering, vacancy rate — and tie `recruitment.Requisition` to specific approved, vacant positions instead of
today's free-standing department/level/grade ask.

**Architecture:** A new Django app `establishment/` owns `Position` (post-numbered, individually persistent across
incumbents) and its multi-step approval workflow (`PositionApprovalStep`, chain shape from
`settings.POSITION_APPROVAL_CHAIN`). It joins `SHARED_KERNEL` in `rbac_audit/test_module_boundaries.py` (same
reasoning as `notifications`). `core_hr.EmployeeVersion` gains a `position` FK (string reference, avoids a circular
import); `recruitment.Requisition` gains a `positions` M2M (direct import — no cycle in that direction) plus
service-layer validation. Occupancy is always derived from `EmployeeVersion`, never stored.

**Tech Stack:** Django 5.2 + DRF (backend, `hcm/backend`), React 19 + TypeScript (frontend, `hcm/frontend`), the
project's existing `TieredModelSerializer`-free plain-`ModelSerializer` + `services.py` business-logic convention.

**Spec:** `docs/superpowers/specs/2026-08-19-position-establishment-design.md` (approved) — this plan implements
every section of it; read both together.

## Global Constraints

- Module boundaries (`hcm/README.md` #1, mechanically enforced by `rbac_audit/test_module_boundaries.py`): domain
  apps may only import `core_hr`/`rbac_audit`/`integrations`/`notifications` (the shared kernel) plus their own
  `queries.py` seam into a peer; shared-kernel apps must never import a domain app back. `establishment` joins the
  shared kernel this plan, so `core_hr`/`recruitment`/any future domain app may import it directly.
- Every new/changed field convention: `TimestampedModel` base, `HistoricalRecords()` on models the spec calls
  auditable, keyword-only service function signatures, `ApprovalError(ValueError)` for state-machine violations
  (never bare `ValueError` from a `services.py` function meant to be caught by a view).
- Role/permission checks live in `views.py` (raise `rest_framework.exceptions.PermissionDenied` → 403);
  `services.py` functions only enforce state-machine validity (raise `ApprovalError` → view catches it → 400). This
  is the established split in `ee_reporting` (`_require_hr_admin` in views, `ApprovalError` in services) — followed
  here even though the spec's prose describes `decide_step` as "checking" the role; the check still happens, just at
  the view layer for correct 403-vs-400 semantics, matching how `ee_reporting.views.ee_review` does the identical
  thing for its own fixed-role step.
- No migration may be written without running `manage.py makemigrations --check --dry-run` clean afterward, and no
  task is done without `manage.py test <app>` (or the relevant frontend suite) passing.

---

### Task 1: `establishment` app skeleton + `Position`/`PositionApprovalStep` models

**Files:**
- Create: `hcm/backend/establishment/__init__.py` (empty)
- Create: `hcm/backend/establishment/apps.py`
- Create: `hcm/backend/establishment/models.py`
- Create: `hcm/backend/establishment/admin.py`
- Create: `hcm/backend/establishment/migrations/__init__.py` (empty)
- Modify: `hcm/backend/config/settings.py` — `INSTALLED_APPS`, new `POSITION_APPROVAL_CHAIN` setting
- Modify: `hcm/backend/rbac_audit/test_module_boundaries.py` — `DOMAIN_APPS`, `SHARED_KERNEL`
- Test: `hcm/backend/establishment/tests.py`

**Interfaces:**
- Produces: `establishment.models.Position` (fields: `post_number`, `title`, `department`, `occupational_level`,
  `job_grade`, `location`, `status`, `current_step`, `proposed_by`; properties `current_occupant`, `is_vacant`;
  manager `Position.objects` with a `.vacant()` queryset method), `establishment.models.PositionApprovalStep`
  (fields: `position`, `step_index`, `role`, `actor`, `decision`, `comment`), `settings.POSITION_APPROVAL_CHAIN`.

- [ ] **Step 1: Write the failing test for `Position` creation and defaults**

```python
# hcm/backend/establishment/tests.py
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import Position


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


def _hr_admin(dept, level, grade, location):
    from django.contrib.auth import get_user_model
    from rbac_audit.models import Role, RoleAssignment

    User = get_user_model()
    emp = Employee.objects.hire(
        employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
        work_email="hradmin@example.com", hire_date=date(2020, 1, 1), department=dept,
        occupational_level=level, job_grade=grade, location=location,
        user=User.objects.create_user(username="hradmin_est", password="x"),
    )
    RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name="hr_admin"))
    return emp


class PositionModelTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_position_defaults_to_draft_with_no_current_step(self):
        position = Position.objects.create(
            post_number="P-00001", title="Software Engineer", department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertEqual(position.current_step, 0)

    def test_post_number_is_unique(self):
        Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location,
        )
        with self.assertRaises(Exception):
            Position.objects.create(
                post_number="P-00001", title="B", department=self.dept, occupational_level=self.level,
                job_grade=self.grade, location=self.location,
            )

    def test_is_vacant_false_when_draft_even_with_no_occupant(self):
        """A draft/in_review position isn't on the establishment yet -- it
        doesn't count as a real vacancy until approved."""
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        self.assertFalse(position.is_vacant)

    def test_is_vacant_true_when_approved_with_no_occupant(self):
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.assertTrue(position.is_vacant)
        self.assertIsNone(position.current_occupant)

    def test_is_vacant_false_once_occupied(self):
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        self.assertFalse(position.is_vacant)
        self.assertIsNotNone(position.current_occupant)

    def test_vacant_queryset_excludes_occupied_and_unapproved(self):
        occupied = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=occupied,
        )
        draft = Position.objects.create(
            post_number="P-00002", title="B", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        vacant = Position.objects.create(
            post_number="P-00003", title="C", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.assertEqual(list(Position.objects.vacant()), [vacant])
        self.assertNotIn(occupied, Position.objects.vacant())
        self.assertNotIn(draft, Position.objects.vacant())
```

Note: `Employee.objects.hire(..., position=position)` doesn't exist yet (Task 4 adds it) — this test file is written
now but only fully passes once Task 4 lands. That's fine: Step 2 below only requires the `Position` model itself to
be missing, which is true right now.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hcm/backend && python manage.py test establishment -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'establishment'` (app doesn't exist yet).

- [ ] **Step 3: Create the app skeleton**

```python
# hcm/backend/establishment/__init__.py
```//empty file

```python
# hcm/backend/establishment/apps.py
from django.apps import AppConfig


class EstablishmentConfig(AppConfig):
    name = "establishment"
    verbose_name = "Position / establishment management (C1)"
```

```python
# hcm/backend/establishment/migrations/__init__.py
```//empty file

- [ ] **Step 4: Write `Position` and `PositionApprovalStep` models**

```python
# hcm/backend/establishment/models.py
"""Position/establishment management (C1, part 1 of 3 -- see
docs/superpowers/specs/2026-08-19-position-establishment-design.md).

A Position is an approved, individually-numbered post, independent of who
currently holds it -- persists across incumbents, matching PFMA-style
establishment control. Occupancy is always DERIVED from `core_hr.
EmployeeVersion.position` (current_occupant/is_vacant below), never stored,
so it can never drift out of sync with who's actually employed.

This app joins SHARED_KERNEL (rbac_audit/test_module_boundaries.py) because
both core_hr (EmployeeVersion.position) and recruitment (Requisition.
positions) need a direct relationship into it, not a queries.py read seam.
"""
from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.db import models
from simple_history.models import HistoricalRecords


class PositionQuerySet(models.QuerySet):
    def vacant(self):
        occupied_ids = EmployeeVersion.objects.filter(
            valid_to__isnull=True, position__isnull=False
        ).values_list("position_id", flat=True)
        return self.filter(status=Position.Status.APPROVED).exclude(id__in=occupied_ids)


class Position(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    post_number = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")
    occupational_level = models.ForeignKey(OccupationalLevel, on_delete=models.PROTECT, related_name="positions")
    job_grade = models.ForeignKey(
        JobGrade, null=True, blank=True, on_delete=models.PROTECT, related_name="positions"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="positions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Index into settings.POSITION_APPROVAL_CHAIN; meaningful only while
    # status == IN_REVIEW (see establishment/services.py).
    current_step = models.PositiveSmallIntegerField(default=0)
    proposed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="positions_proposed"
    )

    objects = PositionQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["post_number"]

    def __str__(self):
        return f"{self.post_number}: {self.title} ({self.get_status_display()})"

    @property
    def current_occupant(self) -> EmployeeVersion | None:
        return (
            EmployeeVersion.objects.filter(valid_to__isnull=True, position=self)
            .select_related("employee")
            .first()
        )

    @property
    def is_vacant(self) -> bool:
        return self.status == self.Status.APPROVED and self.current_occupant is None


class PositionApprovalStep(TimestampedModel):
    """Append-only audit trail, one row per approval-chain decision. `role`
    is a SNAPSHOT of which role this step required (read from settings at
    decision time), not a live reference -- so a later chain change never
    rewrites history. `created_at` (from TimestampedModel) is the decision
    timestamp."""

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="approval_steps")
    step_index = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=40)
    actor = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision = models.CharField(max_length=20, choices=Decision.choices)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["position", "step_index", "created_at"]

    def __str__(self):
        return f"{self.position.post_number} step {self.step_index} ({self.role}): {self.decision}"
```

- [ ] **Step 5: Register the app and add the settings**

```python
# hcm/backend/config/settings.py -- add "establishment" to INSTALLED_APPS,
# right after "notifications" (the other H3-era shared-kernel app):
INSTALLED_APPS = [
    ...
    "notifications",
    "establishment",
    # third-party (OpenAPI schema generation, H3)
    "drf_spectacular",
]
```

Append at the very end of the file, after the Sentry block:

```python
# hcm/backend/config/settings.py -- append at end of file

# Position/establishment approval chain (C1) -- ordered list of role names
# an in-review Position must clear, one at a time, after hr_admin proposes
# and submits it. Deployment-time config, not runtime-editable: different
# environments/orgs can use a different chain length or different roles
# without touching establishment/services.py's state machine. See
# docs/superpowers/specs/2026-08-19-position-establishment-design.md §2.3.
POSITION_APPROVAL_CHAIN = os.environ.get(
    "POSITION_APPROVAL_CHAIN", "comp_manager,accounting_officer"
).split(",")
```

- [ ] **Step 6: Register `establishment` in the module-boundary test**

```python
# hcm/backend/rbac_audit/test_module_boundaries.py -- edit DOMAIN_APPS and SHARED_KERNEL:
DOMAIN_APPS = [
    "core_hr", "rbac_audit", "recruitment", "performance", "learning", "compensation",
    "assessments", "identity_verification", "ee_reporting", "policies", "integrations",
    "notifications", "establishment",
]
...
# notifications joined in H3 on the same reasoning: every domain app calls
# notifications.services.notify() the way it would call integrations.collab,
# and notifications itself knows nothing about agreements/proposals/policies
# as domains, only recipients and message text. establishment joined in C1
# on the same reasoning again: core_hr and recruitment both need a direct
# relationship into it (EmployeeVersion.position, Requisition.positions),
# and establishment itself knows nothing about agreements/proposals/
# applicants as domains, only posts and who's allowed to approve them. The
# kernel test below is what keeps that true: infrastructure may not import
# a domain app back.
SHARED_KERNEL = {"core_hr", "rbac_audit", "integrations", "notifications", "establishment"}
```

- [ ] **Step 7: Write `establishment/admin.py`**

```python
# hcm/backend/establishment/admin.py
from django.contrib import admin

from .models import Position, PositionApprovalStep


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("post_number", "title", "department", "status", "current_step")
    list_filter = ("status", "department")
    search_fields = ("post_number", "title")


@admin.register(PositionApprovalStep)
class PositionApprovalStepAdmin(admin.ModelAdmin):
    list_display = ("position", "step_index", "role", "actor", "decision", "created_at")
    list_filter = ("decision", "role")
```

- [ ] **Step 8: Generate and inspect the migration**

Run: `cd hcm/backend && python manage.py makemigrations establishment`
Expected: creates `establishment/migrations/0001_initial.py` with `Position` and `PositionApprovalStep` tables (and
their `simple_history` historical-model tables). Read the generated file to confirm both models and their FKs are
present before continuing.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test establishment rbac_audit.test_module_boundaries -v 2`
Expected: `test_post_number_is_unique`, `test_position_defaults_to_draft_with_no_current_step`,
`test_is_vacant_false_when_draft_even_with_no_occupant`, `test_is_vacant_true_when_approved_with_no_occupant`,
`rbac_audit.test_module_boundaries` all PASS. `test_is_vacant_false_once_occupied` and
`test_vacant_queryset_excludes_occupied_and_unapproved` still FAIL (need Task 4's `position=` kwarg on
`Employee.objects.hire`) — expected at this point, note it and continue.

- [ ] **Step 10: `manage.py check` and migration-check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: both clean (no new changes detected beyond what Step 8 already created).

- [ ] **Step 11: Commit**

```bash
git add hcm/backend/establishment hcm/backend/config/settings.py hcm/backend/rbac_audit/test_module_boundaries.py
git commit -m "establishment app: Position + PositionApprovalStep models"
```

---

### Task 2: Approval-chain service layer (`establishment/services.py`)

**Files:**
- Create: `hcm/backend/establishment/services.py`
- Test: `hcm/backend/establishment/tests.py` (append)

**Interfaces:**
- Consumes: `establishment.models.Position`, `PositionApprovalStep` (Task 1); `django.conf.settings.
  POSITION_APPROVAL_CHAIN`.
- Produces: `propose_position(*, title, department, occupational_level, job_grade, location, actor=None) ->
  Position`; `submit_for_approval(position, *, actor=None) -> Position`; `decide_step(position, *, actor=None,
  decision, comment="") -> Position`; `revise_and_resubmit(position, *, actor=None, **changed_fields) -> Position`;
  `ApprovalError(ValueError)`.

- [ ] **Step 1: Write the failing tests for the full chain**

```python
# hcm/backend/establishment/tests.py -- append
from django.test import override_settings

from .models import PositionApprovalStep
from .services import ApprovalError, decide_step, propose_position, revise_and_resubmit, submit_for_approval


class ApprovalChainTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def _propose(self):
        return propose_position(
            title="Software Engineer", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location,
        )

    def test_propose_creates_a_draft_with_a_post_number(self):
        position = self._propose()
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertTrue(position.post_number)

    def test_post_numbers_increment_sequentially(self):
        first = self._propose()
        second = self._propose()
        self.assertNotEqual(first.post_number, second.post_number)
        first_n = int("".join(ch for ch in first.post_number if ch.isdigit()))
        second_n = int("".join(ch for ch in second.post_number if ch.isdigit()))
        self.assertEqual(second_n, first_n + 1)

    def test_submit_moves_draft_to_in_review_at_step_zero(self):
        position = self._propose()
        submit_for_approval(position)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.IN_REVIEW)
        self.assertEqual(position.current_step, 0)

    def test_submit_twice_raises(self):
        position = self._propose()
        submit_for_approval(position)
        with self.assertRaises(ApprovalError):
            submit_for_approval(position)

    @override_settings(POSITION_APPROVAL_CHAIN=["comp_manager", "accounting_officer"])
    def test_full_two_step_chain_approves(self):
        position = self._propose()
        submit_for_approval(position)

        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED, comment="looks fine")
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.IN_REVIEW)
        self.assertEqual(position.current_step, 1)

        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.APPROVED)

        steps = list(position.approval_steps.order_by("step_index"))
        self.assertEqual([s.role for s in steps], ["comp_manager", "accounting_officer"])
        self.assertEqual([s.decision for s in steps], ["approved", "approved"])
        self.assertEqual(steps[0].comment, "looks fine")

    @override_settings(POSITION_APPROVAL_CHAIN=["accounting_officer"])
    def test_a_different_shorter_chain_is_honoured_with_no_code_changes(self):
        """This is the test that actually proves 'configurable' holds --
        not just that the default 2-step shape works."""
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.APPROVED)
        self.assertEqual(position.approval_steps.count(), 1)
        self.assertEqual(position.approval_steps.first().role, "accounting_officer")

    def test_rejection_stops_the_chain_immediately(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.REJECTED, comment="wrong grade")
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.REJECTED)
        self.assertEqual(position.approval_steps.count(), 1)

    def test_decide_step_on_a_draft_position_raises(self):
        position = self._propose()
        with self.assertRaises(ApprovalError):
            decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)

    def test_decide_step_on_an_already_approved_position_raises(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        with self.assertRaises(ApprovalError):
            decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)

    def test_revise_and_resubmit_keeps_post_number_and_prior_steps(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.REJECTED, comment="wrong grade")
        original_post_number = position.post_number

        junior_grade = JobGrade.objects.create(
            name="Grade 2", code="G2", occupational_level=self.level
        )
        revise_and_resubmit(position, job_grade=junior_grade)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertEqual(position.current_step, 0)
        self.assertEqual(position.post_number, original_post_number)
        self.assertEqual(position.job_grade, junior_grade)
        self.assertEqual(position.approval_steps.count(), 1)  # the rejection stays on record

    def test_revise_and_resubmit_from_a_non_rejected_position_raises(self):
        position = self._propose()
        with self.assertRaises(ApprovalError):
            revise_and_resubmit(position, title="New title")
```

Add the missing import at the top of the test file: `from .models import Position` (already implicitly needed by
`ApprovalChainTests` via the module-level `Position` reference — confirm it's imported once, not duplicated, since
Task 1's Step 1 already did `from .models import Position`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test establishment.tests.ApprovalChainTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'propose_position' from 'establishment.services'` (module doesn't
exist yet).

- [ ] **Step 3: Write `establishment/services.py`**

```python
# hcm/backend/establishment/services.py
"""Position approval-chain workflow (C1). hr_admin always proposes and
submits; settings.POSITION_APPROVAL_CHAIN governs everything after that --
see docs/superpowers/specs/2026-08-19-position-establishment-design.md §2.

Role/permission checks are NOT done here (see the plan's Global
Constraints) -- these functions only enforce state-machine validity. The
view layer checks who is allowed to call which action and raises
PermissionDenied (403) before ever reaching these functions; a state-
machine violation from here raises ApprovalError, which the view turns
into a 400.
"""
from __future__ import annotations

from django.conf import settings
from django.db import transaction

from .models import Position, PositionApprovalStep


class ApprovalError(ValueError):
    pass


def _next_post_number() -> str:
    last = Position.objects.order_by("-id").values_list("post_number", flat=True).first()
    if last:
        digits = "".join(ch for ch in last if ch.isdigit())
        n = int(digits) + 1 if digits else 1
    else:
        n = 1
    return f"P-{n:05d}"


def propose_position(
    *, title: str, department, occupational_level, job_grade, location, actor=None
) -> Position:
    return Position.objects.create(
        post_number=_next_post_number(), title=title, department=department,
        occupational_level=occupational_level, job_grade=job_grade, location=location,
        proposed_by=actor,
    )


def submit_for_approval(position: Position, *, actor=None) -> Position:
    if position.status != Position.Status.DRAFT:
        raise ApprovalError(f"Only a draft position can be submitted for approval (currently {position.status}).")
    position.status = Position.Status.IN_REVIEW
    position.current_step = 0
    position.save(update_fields=["status", "current_step"])
    return position


@transaction.atomic
def decide_step(position: Position, *, actor=None, decision: str, comment: str = "") -> Position:
    if position.status != Position.Status.IN_REVIEW:
        raise ApprovalError(f"Position {position.post_number} is not currently in review.")
    chain = settings.POSITION_APPROVAL_CHAIN
    if position.current_step >= len(chain):
        raise ApprovalError(f"Position {position.post_number} has no more approval steps configured.")

    role = chain[position.current_step]
    PositionApprovalStep.objects.create(
        position=position, step_index=position.current_step, role=role, actor=actor,
        decision=decision, comment=comment,
    )

    if decision == PositionApprovalStep.Decision.REJECTED:
        position.status = Position.Status.REJECTED
        position.save(update_fields=["status"])
        return position

    next_step = position.current_step + 1
    if next_step >= len(chain):
        position.status = Position.Status.APPROVED
        position.save(update_fields=["status"])
    else:
        position.current_step = next_step
        position.save(update_fields=["current_step"])
    return position


def revise_and_resubmit(position: Position, *, actor=None, **changed_fields) -> Position:
    """hr_admin only (enforced in the view) -- from `rejected`, may update
    title/department/occupational_level/job_grade/location, then restarts
    the chain from step 0. post_number and prior PositionApprovalStep rows
    are kept: this is a new cycle on the same post identity."""
    if position.status != Position.Status.REJECTED:
        raise ApprovalError(f"Only a rejected position can be revised (currently {position.status}).")
    allowed_fields = {"title", "department", "occupational_level", "job_grade", "location"}
    unknown = set(changed_fields) - allowed_fields
    if unknown:
        raise ApprovalError(f"Cannot change these fields via revise_and_resubmit: {', '.join(sorted(unknown))}.")
    for field, value in changed_fields.items():
        setattr(position, field, value)
    position.status = Position.Status.DRAFT
    position.current_step = 0
    position.save(update_fields=[*changed_fields.keys(), "status", "current_step"])
    return position
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test establishment.tests.ApprovalChainTests -v 2`
Expected: all PASS, including the two `@override_settings` tests proving the chain is genuinely configurable.

- [ ] **Step 5: Full app check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run && python manage.py test establishment`
Expected: clean, all tests pass (the two occupancy tests from Task 1 that depend on Task 4 are still expected-fail
at this point).

- [ ] **Step 6: Commit**

```bash
git add hcm/backend/establishment/services.py hcm/backend/establishment/tests.py
git commit -m "establishment: approval-chain service layer (propose/submit/decide/revise)"
```

---

### Task 3: `establishment` API (permissions, serializers, views, urls)

**Files:**
- Create: `hcm/backend/establishment/permissions.py`
- Create: `hcm/backend/establishment/serializers.py`
- Create: `hcm/backend/establishment/views.py`
- Create: `hcm/backend/establishment/urls.py`
- Modify: `hcm/backend/config/urls.py`
- Test: `hcm/backend/establishment/test_api.py`

**Interfaces:**
- Consumes: `establishment.models.Position`, `establishment.services.*` (Task 2), `rbac_audit.drf.
  get_request_employee`, `rbac_audit.permissions.has_role`.
- Produces: `GET/POST /api/v1/positions/`, `POST /api/v1/positions/{id}/submit/`, `POST
  /api/v1/positions/{id}/decide/`, `POST /api/v1/positions/{id}/revise/`.

- [ ] **Step 1: Write the failing API tests**

```python
# hcm/backend/establishment/test_api.py
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Position

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class EstablishmentApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        def _hire(number, username, role_name):
            emp = Employee.objects.hire(
                employee_number=number, first_name=username.title(), last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                user=User.objects.create_user(username=username, password="x"),
            )
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role_name))
            return emp

        self.hr_admin = _hire("HR1", "est_hradmin", "hr_admin")
        self.comp_manager = _hire("CM1", "est_compmanager", "comp_manager")
        self.accounting_officer = _hire("AO1", "est_accountingofficer", "accounting_officer")
        self.recruiter = _hire("REC1", "est_recruiter", "recruiter")
        self.auditor = _hire("AUD1", "est_auditor", "auditor")
        self.line_manager = _hire("LM1", "est_manager", "line_manager")


@override_settings(POSITION_APPROVAL_CHAIN=["comp_manager", "accounting_officer"])
class PositionCreateAndChainApiTests(EstablishmentApiTestCase):
    def _propose(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/positions/", {
            "title": "Software Engineer", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_recruiter_cannot_propose(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/positions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id,
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_full_chain_via_api(self):
        position_id = self._propose()

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/submit/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "in_review")

        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "in_review")

        self.client.force_authenticate(user=self.accounting_officer.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "approved")

    def test_wrong_role_at_a_step_is_403_not_400(self):
        position_id = self._propose()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/positions/{position_id}/submit/")

        self.client.force_authenticate(user=self.accounting_officer.user)  # step 0 needs comp_manager
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_rejection_then_revise_via_api(self):
        position_id = self._propose()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/positions/{position_id}/submit/")

        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            f"/api/v1/positions/{position_id}/decide/", {"decision": "rejected", "comment": "wrong grade"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "rejected")

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/revise/", {"title": "Senior Software Engineer"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["title"], "Senior Software Engineer")


class PositionReadAccessApiTests(EstablishmentApiTestCase):
    def setUp(self):
        super().setUp()
        self.approved = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.draft = Position.objects.create(
            post_number="P-00002", title="B", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )

    def test_hr_admin_sees_every_status(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/positions/")
        ids = {p["id"] for p in response.data["results"]}
        self.assertEqual(ids, {self.approved.id, self.draft.id})

    def test_recruiter_only_sees_approved(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/positions/")
        ids = {p["id"] for p in response.data["results"]}
        self.assertEqual(ids, {self.approved.id})

    def test_line_manager_cannot_read(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/positions/")
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_read(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get("/api/v1/positions/")
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test establishment.test_api -v 2`
Expected: FAIL — 404s (no `/api/v1/positions/` URL registered yet).

- [ ] **Step 3: Write `establishment/permissions.py`**

```python
# hcm/backend/establishment/permissions.py
from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import permissions


class EstablishmentPermission(permissions.BasePermission):
    """Coarse gate, fine-grained per-action in views.py -- same shape as
    ee_reporting.permissions.EEReportingPermission. WRITE_ROLES lets any of
    the three workflow roles reach a POST at this layer; which specific
    action (propose/submit/revise vs. a decide step) each one may actually
    perform is enforced per-action in views.py."""

    READ_ROLES = ("hr_admin", "comp_manager", "accounting_officer", "auditor", "recruiter")
    WRITE_ROLES = ("hr_admin", "comp_manager", "accounting_officer")

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        if employee is None:
            return False
        roles = self.READ_ROLES if request.method in permissions.SAFE_METHODS else self.WRITE_ROLES
        return any(has_role(employee, r) for r in roles)
```

- [ ] **Step 4: Write `establishment/serializers.py`**

```python
# hcm/backend/establishment/serializers.py
from __future__ import annotations

from rest_framework import serializers

from .models import Position, PositionApprovalStep


class PositionApprovalStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionApprovalStep
        fields = ["id", "step_index", "role", "actor", "decision", "comment", "created_at"]


class PositionSerializer(serializers.ModelSerializer):
    approval_steps = PositionApprovalStepSerializer(many=True, read_only=True)
    is_vacant = serializers.BooleanField(read_only=True)
    current_incumbent_number = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = [
            "id", "post_number", "title", "department", "occupational_level", "job_grade", "location",
            "status", "current_step", "proposed_by", "approval_steps", "is_vacant", "current_incumbent_number",
        ]
        read_only_fields = ["post_number", "status", "current_step", "proposed_by"]

    def get_current_incumbent_number(self, obj) -> str | None:
        occupant = obj.current_occupant
        return occupant.employee.employee_number if occupant else None
```

- [ ] **Step 5: Write `establishment/views.py`**

```python
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
        position = propose_position(actor=actor, **{
            k: v for k, v in serializer.validated_data.items()
        })
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
        changed = {k: v for k, v in request.data.items() if k in allowed_fields}
        try:
            revise_and_resubmit(position, actor=actor, **changed)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(position).data)
```

- [ ] **Step 6: Write `establishment/urls.py`**

```python
# hcm/backend/establishment/urls.py
from rest_framework.routers import DefaultRouter

from .views import PositionViewSet

router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")

urlpatterns = router.urls
```

- [ ] **Step 7: Mount the URLs**

```python
# hcm/backend/config/urls.py -- add alongside the other module includes:
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("establishment.urls")),
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test establishment -v 2`
Expected: all PASS (`PositionCreateAndChainApiTests`, `PositionReadAccessApiTests`,
`test_wrong_role_at_a_step_is_403_not_400` in particular confirms the view-layer-check design decision works).

- [ ] **Step 9: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: clean.

- [ ] **Step 10: Commit**

```bash
git add hcm/backend/establishment/permissions.py hcm/backend/establishment/serializers.py hcm/backend/establishment/views.py hcm/backend/establishment/urls.py hcm/backend/establishment/test_api.py hcm/backend/config/urls.py
git commit -m "establishment: Position API (propose/submit/decide/revise, role-scoped reads)"
```

---

### Task 4: `EmployeeVersion.position` field + carry-forward on version transitions

**Files:**
- Modify: `hcm/backend/core_hr/models.py`
- Modify: `hcm/backend/rbac_audit/tiers.py`
- Create: `hcm/backend/core_hr/migrations/0006_employeeversion_position.py` (generated)
- Test: `hcm/backend/core_hr/tests.py` (append)

**Interfaces:**
- Consumes: `establishment.models.Position` (string reference only, Task 1).
- Produces: `EmployeeVersion.position` (nullable FK); `Employee.objects.hire(..., position=None)` kwarg;
  `VERSION_CARRY_FIELDS` includes `"position"`.

- [ ] **Step 1: Write the failing tests**

```python
# hcm/backend/core_hr/tests.py -- append (this file already has _seed_reference_data() -- reuse it)
from establishment.models import Position


class EmployeeVersionPositionTests(TestCase):
    def setUp(self):
        self.dept_a, _, self.level_top, self.grade, self.location = _seed_reference_data()
        self.position = Position.objects.create(
            post_number="P-00001", title="Engineer", department=self.dept_a, occupational_level=self.level_top,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )

    def test_hire_can_link_a_position(self):
        employee = Employee.objects.hire(
            employee_number="E0050", first_name="Pos", last_name="Itioned", date_of_birth=date(1990, 1, 1),
            work_email="pos.itioned@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        self.assertEqual(employee.current_version.position_id, self.position.id)

    def test_hire_without_a_position_still_works(self):
        """Backward compatibility: every existing caller (bulk import, seed
        data, other tests) omits position entirely."""
        employee = Employee.objects.hire(
            employee_number="E0051", first_name="No", last_name="Position", date_of_birth=date(1990, 1, 1),
            work_email="no.position@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location,
        )
        self.assertIsNone(employee.current_version.position_id)

    def test_position_carries_forward_across_a_promotion(self):
        """Regression guard: VERSION_CARRY_FIELDS must include 'position',
        or a promotion/transfer/grade-change silently vacates the post even
        though the employee never actually left it."""
        employee = Employee.objects.hire(
            employee_number="E0052", first_name="Carried", last_name="Forward", date_of_birth=date(1990, 1, 1),
            work_email="carried.forward@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.GRADE_CHANGE, effective_date=date(2025, 1, 1),
        )
        self.assertEqual(employee.current_version.position_id, self.position.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test core_hr.tests.EmployeeVersionPositionTests -v 2`
Expected: FAIL — `TypeError: hire() got an unexpected keyword argument 'position'`.

- [ ] **Step 3: Add the field to `EmployeeVersion`**

```python
# hcm/backend/core_hr/models.py -- in EmployeeVersion, right after the `location` field (~line 331):
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="employee_versions"
    )
    # String reference, not a direct import: establishment/models.py imports
    # core_hr for its own FKs, so a direct import here would be circular.
    # Django resolves string FKs lazily via the app registry -- core_hr
    # needs no production import of establishment at all for this to work.
    position = models.ForeignKey(
        "establishment.Position", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="employee_versions",
    )
```

- [ ] **Step 4: Add `position` to `VERSION_CARRY_FIELDS` and the `hire()` kwarg**

```python
# hcm/backend/core_hr/models.py -- VERSION_CARRY_FIELDS (~line 177):
VERSION_CARRY_FIELDS = (
    "department", "job_title", "occupational_level", "job_grade", "manager",
    "employment_status", "citizenship_status", "location", "position",
    "race", "gender", "disability_status", "disability_detail",
    "race_source", "disability_source",
)
```

```python
# hcm/backend/core_hr/models.py -- EmployeeManager.hire() signature (~line 101-129), add position=None:
    def hire(
        self,
        *,
        employee_number,
        first_name,
        last_name,
        date_of_birth,
        work_email,
        hire_date,
        department,
        occupational_level,
        location,
        employment_status=None,
        citizenship_status=None,
        job_grade=None,
        manager=None,
        position=None,
        race=None,
        gender=None,
        disability_status=None,
        disability_detail="",
        race_source=None,
        disability_source=None,
        preferred_name="",
        national_id_number="",
        passport_number="",
        personal_email="",
        phone="",
        user=None,
    ):
```

```python
# hcm/backend/core_hr/models.py -- inside hire(), the EmployeeVersion.objects.create(...) call (~line 148-166),
# add position=position after location=location:
        version = EmployeeVersion.objects.create(
            employee=employee,
            valid_from=hire_date,
            valid_to=None,
            department=department,
            occupational_level=occupational_level,
            job_grade=job_grade,
            manager=manager,
            employment_status=employment_status or EmployeeVersion.EmploymentStatus.PERMANENT,
            citizenship_status=citizenship_status
            or EmployeeVersion.CitizenshipStatus.SA_CITIZEN_BIRTH_DESCENT,
            location=location,
            position=position,
            race=race or EmployeeVersion.Race.NOT_DISCLOSED,
            gender=gender or EmployeeVersion.Gender.NOT_DISCLOSED,
            disability_status=disability_status or EmployeeVersion.DisabilityStatus.NOT_DISCLOSED,
            disability_detail=disability_detail,
            race_source=race_source or EmployeeVersion.DemographicSource.IMPORTED,
            disability_source=disability_source or EmployeeVersion.DemographicSource.IMPORTED,
        )
```

- [ ] **Step 5: Add the field tier**

```python
# hcm/backend/rbac_audit/tiers.py -- in FIELD_TIERS["core_hr.EmployeeVersion"], right after "department":
    "core_hr.EmployeeVersion": {
        "department": FieldTier.PUBLIC,
        "job_title": FieldTier.PUBLIC,
        "position": FieldTier.PUBLIC,
        "occupational_level": FieldTier.INTERNAL,
        ...
```

- [ ] **Step 6: Generate the migration**

Run: `cd hcm/backend && python manage.py makemigrations core_hr`
Expected: creates `core_hr/migrations/0006_employeeversion_position.py` (naming may differ slightly — use whatever
Django generates) with an `AddField` for `position` and a dependency on `establishment.0001_initial`. Open the file
and confirm the dependency line lists `("establishment", "0001_initial")` — if Django didn't infer it automatically
(it usually does, from the string FK), add it manually to `dependencies`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test core_hr establishment -v 2`
Expected: all PASS, including the two previously-blocked `establishment.tests.PositionModelTests` tests from Task 1
(`test_is_vacant_false_once_occupied`, `test_vacant_queryset_excludes_occupied_and_unapproved`).

- [ ] **Step 8: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run && python manage.py test`
Expected: clean; full existing suite still green (this step touches shared model code, so run everything, not just
the two apps).

- [ ] **Step 9: Commit**

```bash
git add hcm/backend/core_hr/models.py hcm/backend/core_hr/migrations hcm/backend/core_hr/tests.py hcm/backend/rbac_audit/tiers.py
git commit -m "core_hr: EmployeeVersion.position (string FK) + carry-forward + PUBLIC tier"
```

---

### Task 5: Backfill Positions for currently-employed staff

**Files:**
- Modify: `hcm/backend/establishment/services.py`
- Create: `hcm/backend/establishment/migrations/0002_backfill_existing_employees.py` (hand-written, thin wrapper)
- Test: `hcm/backend/establishment/tests.py` (append)

**Interfaces:**
- Consumes: `core_hr.models.Employee`, `EmployeeVersion` (real model imports — see rationale below).
- Produces: `establishment.services.backfill_positions_for_current_employees() -> int` (returns count created).

Note on real-model imports in this migration: every other data migration in this codebase (e.g.
`rbac_audit/migrations/0007_seed_default_retention_rules.py`) uses `apps.get_model(...)` historical state, which is
right for a generically-replayed seed. This migration is different — a one-time backfill tightly coupled to this
feature's rollout, not something meant to be replayed against an arbitrary historical schema. The backfill logic is
written as a normal, directly-testable service function using real model imports (so it can be unit-tested against
real fixtures in milliseconds, not through migration-replay machinery), and the migration file is a thin
`RunPython` wrapper that calls it.

- [ ] **Step 1: Write the failing test**

```python
# hcm/backend/establishment/tests.py -- append
from .services import backfill_positions_for_current_employees


class BackfillTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def _hire(self, number):
        return Employee.objects.hire(
            employee_number=number, first_name="Backfill", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_creates_one_approved_position_per_current_employee(self):
        e1 = self._hire("E0060")
        e2 = self._hire("E0061")

        created = backfill_positions_for_current_employees()

        self.assertEqual(created, 2)
        self.assertEqual(Position.objects.count(), 2)
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertIsNotNone(e1.current_version.position_id)
        self.assertIsNotNone(e2.current_version.position_id)
        self.assertNotEqual(e1.current_version.position_id, e2.current_version.position_id)
        for position in Position.objects.all():
            self.assertEqual(position.status, Position.Status.APPROVED)
            self.assertEqual(position.approval_steps.count(), 0)

    def test_two_employees_with_identical_role_get_separate_positions(self):
        """1:1, never shared/grouped -- a Position is one seat."""
        self._hire("E0062")
        self._hire("E0063")
        backfill_positions_for_current_employees()
        post_numbers = set(Position.objects.values_list("post_number", flat=True))
        self.assertEqual(len(post_numbers), 2)

    def test_is_idempotent(self):
        self._hire("E0064")
        first_count = backfill_positions_for_current_employees()
        second_count = backfill_positions_for_current_employees()
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)  # already-linked EmployeeVersions are skipped
        self.assertEqual(Position.objects.count(), 1)

    def test_employee_with_no_current_version_is_skipped_not_errored(self):
        """Orphan records (core_hr's own Sprint-1 data-quality case) must
        not crash the backfill."""
        Employee.objects.create(
            employee_number="E0065", first_name="Orphan", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email="orphan.case@example.com", hire_date=date(2020, 1, 1),
        )
        created = backfill_positions_for_current_employees()
        self.assertEqual(created, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hcm/backend && python manage.py test establishment.tests.BackfillTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'backfill_positions_for_current_employees'`.

- [ ] **Step 3: Write the backfill function**

```python
# hcm/backend/establishment/services.py -- append
from core_hr.models import Employee


def backfill_positions_for_current_employees() -> int:
    """One-time backfill (called from migration 0002): creates exactly one
    approved Position per currently-employed EmployeeVersion that doesn't
    already have one -- 1:1, never grouped/shared even where department+
    grade+title match exactly, since a Position is one seat. No
    PositionApprovalStep rows are fabricated -- this is already-real
    employment, not a new proposal going through review. Idempotent:
    already-linked EmployeeVersions are skipped, safe to call more than
    once (e.g. if the migration is re-run in a dev environment)."""
    created = 0
    for employee in Employee.objects.all():
        version = employee.current_version
        if version is None or version.position_id is not None:
            continue
        position = Position.objects.create(
            post_number=_next_post_number(),
            title=version.job_title,
            department=version.department,
            occupational_level=version.occupational_level,
            job_grade=version.job_grade,
            location=version.location,
            status=Position.Status.APPROVED,
        )
        version.position = position
        version.save(update_fields=["position"])
        created += 1
    return created
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd hcm/backend && python manage.py test establishment.tests.BackfillTests -v 2`
Expected: all PASS.

- [ ] **Step 5: Write the migration wrapper**

```python
# hcm/backend/establishment/migrations/0002_backfill_existing_employees.py
"""One-time backfill: one approved Position per currently-employed
EmployeeVersion, so approved-vs-filled/vacancy-rate is meaningful from day
one, not just for hires made after this feature ships. See
establishment/services.py::backfill_positions_for_current_employees for
the logic and why this uses real model imports rather than apps.get_model
historical state (docs/superpowers/plans/2026-08-19-position-establishment.md,
Task 5)."""
from django.db import migrations


def backfill(apps, schema_editor):
    from establishment.services import backfill_positions_for_current_employees

    backfill_positions_for_current_employees()


def noop_reverse(apps, schema_editor):
    # Deliberately not reversed: unlinking EmployeeVersion.position and
    # deleting the backfilled Position rows on a reverse migration would
    # destroy real establishment data a user may have built on top of by
    # then (later Positions referencing these, approval history, etc.).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("establishment", "0001_initial"),
        ("core_hr", "0006_employeeversion_position"),
    ]

    operations = [migrations.RunPython(backfill, noop_reverse)]
```

Note: confirm the `core_hr` dependency migration name matches whatever Task 4 Step 6 actually generated (it may not
be exactly `0006_employeeversion_position` — use the real filename).

- [ ] **Step 6: Run the migration against a real (non-test) database check**

Run: `cd hcm/backend && python manage.py migrate establishment`
Expected: `Applying establishment.0002_backfill_existing_employees... OK` — on an empty dev DB this creates 0
positions (no employees yet); that's correct, not a bug. The 151-employee correctness proof is `BackfillTests`
above, which creates its own fixtures.

- [ ] **Step 7: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run && python manage.py test establishment core_hr`
Expected: clean, all pass.

- [ ] **Step 8: Commit**

```bash
git add hcm/backend/establishment/services.py hcm/backend/establishment/migrations/0002_backfill_existing_employees.py hcm/backend/establishment/tests.py
git commit -m "establishment: backfill one approved Position per current employee"
```

---

### Task 6: `Requisition.positions` (M2M) + validation service

**Files:**
- Modify: `hcm/backend/recruitment/models.py`
- Modify: `hcm/backend/recruitment/services.py`
- Modify: `hcm/backend/recruitment/serializers.py`
- Create: `hcm/backend/recruitment/migrations/000X_requisition_positions.py` (generated, name TBD by Django)
- Test: `hcm/backend/recruitment/tests.py` (append), `hcm/backend/recruitment/test_api.py` (append, Step 9)

**Interfaces:**
- Consumes: `establishment.models.Position` (direct import — no circularity in this direction).
- Produces: `Requisition.positions` (M2M); `recruitment.services.validate_requisition_positions(positions, *,
  headcount, requisition=None) -> None` (raises `ValueError`).

- [ ] **Step 1: Write the failing service-layer tests**

`recruitment` already splits its tests: `recruitment/tests.py` for model/service-layer tests,
`recruitment/test_api.py` for API-level tests (confirmed — both files already exist). This task's Step 1 goes in
`tests.py`; Step 9's API tests go in `test_api.py`.

`recruitment/tests.py` already has a module-level `_seed_reference_data()` (dept="Engineering"/"ENG",
level="TOP", grade="Grade 1"/"G1", location="Head Office"/"HO") and already imports `Employee` at module level —
reuse both rather than redefining. Only the imports below and a new `_approved_position` helper are new.

```python
# hcm/backend/recruitment/tests.py -- append (Employee, _seed_reference_data already imported/defined above)
from establishment.models import Position

from .services import validate_requisition_positions


def _approved_position(post_number, dept, level, grade, location):
    return Position.objects.create(
        post_number=post_number, title="Call Centre Agent", department=dept, occupational_level=level,
        job_grade=grade, location=location, status=Position.Status.APPROVED,
    )


class ValidateRequisitionPositionsTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_matching_count_of_approved_vacant_positions_is_valid(self):
        positions = [
            _approved_position(f"P-{i:05d}", self.dept, self.level, self.grade, self.location) for i in range(3)
        ]
        validate_requisition_positions(positions, headcount=3)  # must not raise

    def test_count_mismatch_raises(self):
        positions = [_approved_position("P-00001", self.dept, self.level, self.grade, self.location)]
        with self.assertRaises(ValueError):
            validate_requisition_positions(positions, headcount=2)

    def test_unapproved_position_raises(self):
        position = Position.objects.create(
            post_number="P-00001", title="X", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_already_occupied_position_raises(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        Employee.objects.hire(
            employee_number="E001", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="a.b@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_position_already_claimed_by_another_open_requisition_raises(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        other = Requisition.objects.create(
            title="Other req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        other.positions.add(position)
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_position_claimed_by_a_closed_requisition_is_available_again(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        other = Requisition.objects.create(
            title="Other req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.CLOSED,
        )
        other.positions.add(position)
        validate_requisition_positions([position], headcount=1)  # must not raise

    def test_already_linked_position_is_allowed_even_once_filled(self):
        """A position this SAME requisition already claimed stays valid
        even after it's since been filled by one of the requisition's own
        hires -- an unrelated later PATCH must not be rejected just
        because is_vacant flipped to False for an already-committed post."""
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        requisition = Requisition.objects.create(
            title="Req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        requisition.positions.add(position)
        Employee.objects.hire(
            employee_number="E001", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="a.b@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        validate_requisition_positions([position], headcount=1, requisition=requisition)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test recruitment.tests.ValidateRequisitionPositionsTests -v 2`
Expected: FAIL — `AttributeError`/`ImportError` (no `positions` field, no `validate_requisition_positions`).

- [ ] **Step 3: Add the M2M field**

```python
# hcm/backend/recruitment/models.py -- add import and field
from establishment.models import Position  # direct import: no cycle, establishment never imports recruitment back

...

class Requisition(TimestampedModel):
    ...
    headcount = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Which specific approved, vacant posts this requisition targets (C1) --
    # M2M, not a single FK: headcount can already be >1 (several identical
    # hires), so one requisition may claim several identical vacant posts
    # at once. See docs/superpowers/specs/2026-08-19-position-establishment-design.md §4.2.
    positions = models.ManyToManyField(Position, related_name="requisitions", blank=True)
    hiring_manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="requisitions_managed"
    )
```

- [ ] **Step 4: Write `validate_requisition_positions`**

```python
# hcm/backend/recruitment/services.py -- add near the top, after imports
from establishment.models import Position


def validate_requisition_positions(positions, *, headcount: int, requisition=None) -> None:
    """Raises ValueError (caught by the serializer, surfaced as a 400) if
    the linked positions don't satisfy C1's establishment-control rules.
    Already-linked positions (requisition.positions before this call) are
    exempt from the approved/vacant/unclaimed checks -- a position this
    SAME requisition already committed to stays valid even once one of its
    own hires has since filled it; only newly-added positions are held to
    the strict bar."""
    if len(positions) != headcount:
        raise ValueError(
            f"{len(positions)} position(s) linked but headcount is {headcount} -- they must match."
        )

    already_linked_ids = set(requisition.positions.values_list("id", flat=True)) if requisition else set()

    for position in positions:
        if position.id in already_linked_ids:
            continue
        if position.status != Position.Status.APPROVED:
            raise ValueError(f"Position {position.post_number} is not approved yet.")
        if not position.is_vacant:
            raise ValueError(f"Position {position.post_number} is not vacant.")
        claimed_by = position.requisitions.exclude(
            status__in=[Requisition.Status.CLOSED, Requisition.Status.FILLED]
        )
        if requisition is not None:
            claimed_by = claimed_by.exclude(pk=requisition.pk)
        if claimed_by.exists():
            raise ValueError(f"Position {position.post_number} is already linked to another open requisition.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test recruitment.tests.ValidateRequisitionPositionsTests -v 2`
Expected: FAIL still on the M2M-dependent tests (`test_already_linked_position_is_allowed_even_once_filled` needs
`position=position` on `Employee.objects.hire`, already added in Task 4 — should pass) — actually all should PASS
now since Task 4 already landed the `position=` kwarg. If any fail, check the migration from Step 7 below hasn't
been generated yet — the M2M field needs its migration before `Requisition.objects.create(...)` +
`.positions.add(...)` works in tests.

- [ ] **Step 6: Generate the migration**

Run: `cd hcm/backend && python manage.py makemigrations recruitment`
Expected: creates a migration adding the `positions` M2M field (through-table), depending on
`establishment.0001_initial`.

- [ ] **Step 7: Re-run tests to confirm they now pass**

Run: `cd hcm/backend && python manage.py test recruitment.tests.ValidateRequisitionPositionsTests -v 2`
Expected: all PASS.

- [ ] **Step 8: Wire validation into the serializer**

```python
# hcm/backend/recruitment/serializers.py -- add import
from .services import validate_requisition_positions


class RequisitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Requisition
        fields = [
            "id", "title", "department", "occupational_level", "job_grade", "location",
            "headcount", "status", "hiring_manager", "created_by", "positions",
            "opened_at", "target_fill_date", "closed_at",
        ]
        read_only_fields = ["created_by", "closed_at"]

    def validate(self, attrs):
        positions = attrs.get("positions")
        if positions is None:
            positions = list(self.instance.positions.all()) if self.instance else []
        headcount = attrs.get("headcount", self.instance.headcount if self.instance else 1)
        if not positions:
            raise serializers.ValidationError(
                {"positions": "At least one approved, vacant position is required."}
            )
        try:
            validate_requisition_positions(list(positions), headcount=headcount, requisition=self.instance)
        except ValueError as exc:
            raise serializers.ValidationError({"positions": str(exc)})
        return attrs
```

- [ ] **Step 9: Write the API-level tests**

`recruitment/test_api.py` already has a `RecruitmentApiTestCase` base class (`setUp` creates `self.client`,
`self.dept`/`self.level`/`self.grade`/`self.location`, `self.recruiter`, `self.hr_admin`, `self.plain_employee`, and
`self.requisition`/`self.applicant` fixtures) — subclass it rather than rebuilding login/reference-data setup.

```python
# hcm/backend/recruitment/test_api.py -- append
from establishment.models import Position


class RequisitionPositionValidationApiTests(RecruitmentApiTestCase):
    def setUp(self):
        super().setUp()
        self.position = Position.objects.create(
            post_number="P-00001", title="Agent", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )

    def test_create_without_positions_is_rejected(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/requisitions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id, "headcount": 1, "status": "open",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("positions", response.data)

    def test_create_with_matching_approved_vacant_position_succeeds(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/requisitions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id, "headcount": 1, "status": "open",
            "positions": [self.position.id],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
```

Note: `self.requisition` (from the base class's own `setUp`, line ~52 of the existing file) is created via
`Requisition.objects.create(...)` directly at the ORM level, not through `RequisitionSerializer` — Django's ORM
`.create()` never runs DRF serializer validation, so that existing fixture is unaffected by Task 6 Step 8's new
`validate()` method and needs no changes.

- [ ] **Step 10: Run the API tests**

Run: `cd hcm/backend && python manage.py test recruitment -v 2`
Expected: all PASS, including every pre-existing `recruitment` test (the `RequisitionSerializer.validate` addition
must not break any test that previously created a `Requisition` without positions — if any do break, they predate
this feature and need `positions=[...]` added to their fixture; check with `git log` before editing an old test to
confirm it's a legitimate fixture gap, not a real regression).

- [ ] **Step 11: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: clean.

- [ ] **Step 12: Commit**

```bash
git add hcm/backend/recruitment/models.py hcm/backend/recruitment/services.py hcm/backend/recruitment/serializers.py hcm/backend/recruitment/migrations hcm/backend/recruitment/tests.py hcm/backend/recruitment/test_api.py
git commit -m "recruitment: Requisition.positions (M2M) + establishment-control validation"
```

---

### Task 7: Hire flow — auto-assign a specific vacant linked position

**Files:**
- Modify: `hcm/backend/recruitment/services.py`
- Test: `hcm/backend/recruitment/tests.py` (append)

**Interfaces:**
- Consumes: `Requisition.positions` (Task 6), `Employee.objects.hire(..., position=...)` (Task 4).
- Produces: `_complete_hire` now passes a resolved `Position` through to `Employee.objects.hire`.

- [ ] **Step 1: Write the failing tests**

`Applicant` and `transition_applicant` are already imported at the top of `recruitment/tests.py` — no new imports
needed for this test class.

```python
# hcm/backend/recruitment/tests.py -- append
class HireAssignsPositionTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.p1 = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        self.p2 = _approved_position("P-00002", self.dept, self.level, self.grade, self.location)
        self.requisition = Requisition.objects.create(
            title="Agent", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=2, status=Requisition.Status.OPEN,
        )
        self.requisition.positions.set([self.p1, self.p2])

    def _applicant(self, number):
        return Applicant.objects.create(
            requisition=self.requisition, first_name="App", last_name=number, email=f"{number}@example.com",
            date_of_birth=date(1995, 1, 1), current_stage=Applicant.Stage.OFFER,
        )

    def test_first_hire_takes_the_lowest_post_number(self):
        applicant = self._applicant("A")
        transition_applicant(applicant, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))
        applicant.refresh_from_db()
        self.assertEqual(applicant.resulting_employee.current_version.position_id, self.p1.id)

    def test_second_sequential_hire_takes_the_next_still_vacant_position(self):
        first = self._applicant("A")
        transition_applicant(first, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))

        second = self._applicant("B")
        transition_applicant(second, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 2))
        second.refresh_from_db()
        self.assertEqual(second.resulting_employee.current_version.position_id, self.p2.id)

    def test_requisition_auto_fills_once_every_linked_position_is_occupied(self):
        first = self._applicant("A")
        transition_applicant(first, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))
        second = self._applicant("B")
        transition_applicant(second, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 2))

        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.FILLED)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test recruitment.tests.HireAssignsPositionTests -v 2`
Expected: FAIL — `AssertionError: None != <position id>` (hire doesn't resolve/pass a position yet).

- [ ] **Step 3: Update `_complete_hire`**

```python
# hcm/backend/recruitment/services.py -- inside _complete_hire, before the retry loop
# that calls Employee.objects.hire(...) (~line 64-90):
def _complete_hire(applicant: Applicant, *, hire_date) -> Employee:
    requisition = applicant.requisition

    if Employee.objects.filter(work_email=applicant.email).exists():
        raise ValueError(f"An employee with work email '{applicant.email}' already exists — cannot complete hire.")

    # Which specific linked position does THIS hire consume? The
    # requisition's still-vacant linked positions, lowest post_number
    # first -- positions grouped into one requisition are by definition
    # interchangeable for this purpose (if they weren't, they'd belong in
    # separate requisitions). None for requisitions predating C1 (no
    # linked positions at all).
    position = (
        requisition.positions.filter(id__in=Position.objects.vacant().values("id"))
        .order_by("post_number")
        .first()
    )

    employee = None
    for _attempt in range(5):
        employee_number = _next_employee_number()
        try:
            with transaction.atomic():
                employee = Employee.objects.hire(
                    employee_number=employee_number,
                    first_name=applicant.first_name,
                    last_name=applicant.last_name,
                    date_of_birth=applicant.date_of_birth,
                    work_email=applicant.email,
                    hire_date=hire_date,
                    department=requisition.department,
                    occupational_level=requisition.occupational_level,
                    job_grade=requisition.job_grade,
                    location=requisition.location,
                    manager=requisition.hiring_manager,
                    position=position,
                    race=applicant.race,
                    gender=applicant.gender,
                    disability_status=applicant.disability_status,
                    race_source=EmployeeVersion.DemographicSource.SELF_IDENTIFIED,
                    disability_source=EmployeeVersion.DemographicSource.SELF_IDENTIFIED,
                )
        except IntegrityError:
            continue
        else:
            break
    if employee is None:
        raise RuntimeError("Could not allocate a unique employee number after 5 attempts")

    applicant.resulting_employee = employee
    applicant.save(update_fields=["resulting_employee"])
```

Add the import at the top of the file: `from establishment.models import Position` (already present after Task 6
Step 4 — confirm it's not duplicated).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test recruitment.tests.HireAssignsPositionTests -v 2`
Expected: all PASS. `test_requisition_auto_fills_once_every_linked_position_is_occupied` should already pass with
zero changes to the FILLED-transition logic (`recruitment/services.py`'s existing `hired_count >= headcount` check,
untouched) — this test is what proves that claim from the spec (§4.3) actually holds.

- [ ] **Step 5: Full recruitment + core_hr suite**

Run: `cd hcm/backend && python manage.py test recruitment core_hr establishment -v 2`
Expected: all PASS, no regressions.

- [ ] **Step 6: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: clean (no model changes this task, so no new migration expected).

- [ ] **Step 7: Commit**

```bash
git add hcm/backend/recruitment/services.py hcm/backend/recruitment/tests.py
git commit -m "recruitment: hire flow auto-assigns the next vacant linked position"
```

---

### Task 8: Backfill historical closed/filled Requisitions

**Files:**
- Modify: `hcm/backend/recruitment/services.py`
- Create: `hcm/backend/recruitment/migrations/000Y_backfill_requisition_positions.py` (hand-written, name TBD)
- Test: `hcm/backend/recruitment/tests.py` (append)

**Interfaces:**
- Consumes: `establishment.models.Position`, `recruitment.models.Requisition`/`Applicant` (real model imports, same
  rationale as Task 5).
- Produces: `recruitment.services.backfill_requisition_positions() -> int`.

- [ ] **Step 1: Write the failing test**

```python
# hcm/backend/recruitment/tests.py -- append
from .services import backfill_requisition_positions


class BackfillRequisitionPositionsTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_closed_requisition_with_a_resulting_hire_gets_linked(self):
        requisition = Requisition.objects.create(
            title="Legacy", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.FILLED,
        )
        employee = Employee.objects.hire(
            employee_number="E0070", first_name="Legacy", last_name="Hire", date_of_birth=date(1990, 1, 1),
            work_email="legacy.hire@example.com", hire_date=date(2023, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        applicant = Applicant.objects.create(
            requisition=requisition, first_name="Legacy", last_name="Hire", email="legacy.hire@example.com",
            date_of_birth=date(1990, 1, 1), current_stage=Applicant.Stage.HIRED, resulting_employee=employee,
        )
        # this employee predates C1 -- backfill their position first, same
        # as establishment.services.backfill_positions_for_current_employees
        from establishment.services import backfill_positions_for_current_employees

        backfill_positions_for_current_employees()
        employee.refresh_from_db()
        backfilled_position_id = employee.current_version.position_id
        self.assertIsNotNone(backfilled_position_id)

        linked = backfill_requisition_positions()

        self.assertEqual(linked, 1)
        requisition.refresh_from_db()
        self.assertEqual(list(requisition.positions.values_list("id", flat=True)), [backfilled_position_id])

    def test_open_requisition_with_no_resulting_hire_is_left_unlinked(self):
        Requisition.objects.create(
            title="Still open", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        linked = backfill_requisition_positions()
        self.assertEqual(linked, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hcm/backend && python manage.py test recruitment.tests.BackfillRequisitionPositionsTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'backfill_requisition_positions'`.

- [ ] **Step 3: Write the function**

```python
# hcm/backend/recruitment/services.py -- append
def backfill_requisition_positions() -> int:
    """One-time backfill (called from a migration): a CLOSED/FILLED
    requisition whose resulting hire now has a backfilled Position
    (establishment.services.backfill_positions_for_current_employees, run
    first) gets that Position linked. Requisitions with no resulting hire
    predate establishment control entirely and stay unlinked. Idempotent:
    already-linked requisitions are skipped."""
    linked = 0
    closed_statuses = [Requisition.Status.CLOSED, Requisition.Status.FILLED]
    for requisition in Requisition.objects.filter(status__in=closed_statuses):
        if requisition.positions.exists():
            continue
        hired = requisition.applicants.filter(
            current_stage=Applicant.Stage.HIRED, resulting_employee__isnull=False
        ).select_related("resulting_employee")
        for applicant in hired:
            version = applicant.resulting_employee.current_version
            if version is not None and version.position_id is not None:
                requisition.positions.add(version.position_id)
                linked += 1
                break  # one linked position is enough to mark this requisition backfilled
    return linked
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd hcm/backend && python manage.py test recruitment.tests.BackfillRequisitionPositionsTests -v 2`
Expected: both PASS.

- [ ] **Step 5: Write the migration wrapper**

```python
# hcm/backend/recruitment/migrations/000Y_backfill_requisition_positions.py
# (replace 000Y with the next real number in hcm/backend/recruitment/migrations/)
"""One-time backfill: links each historical CLOSED/FILLED requisition to
the Position its resulting hire was backfilled into by
establishment.0002_backfill_existing_employees, which MUST run first (see
the dependency below). See recruitment/services.py::
backfill_requisition_positions and docs/superpowers/plans/
2026-08-19-position-establishment.md Task 8."""
from django.db import migrations


def backfill(apps, schema_editor):
    from recruitment.services import backfill_requisition_positions

    backfill_requisition_positions()


def noop_reverse(apps, schema_editor):
    pass  # same reasoning as establishment.0002 -- don't destroy real linkage on a reverse


class Migration(migrations.Migration):
    dependencies = [
        ("recruitment", "000X_requisition_positions"),  # the M2M-adding migration from Task 6 Step 6 -- use its real name
        ("establishment", "0002_backfill_existing_employees"),
    ]

    operations = [migrations.RunPython(backfill, noop_reverse)]
```

- [ ] **Step 6: Run the migration against the dev database**

Run: `cd hcm/backend && python manage.py migrate recruitment`
Expected: applies cleanly.

- [ ] **Step 7: Full check**

Run: `cd hcm/backend && python manage.py check && python manage.py makemigrations --check --dry-run && python manage.py test`
Expected: clean; full backend suite green (this is the last backend-only task — a good point to run everything).

- [ ] **Step 8: Commit**

```bash
git add hcm/backend/recruitment/services.py hcm/backend/recruitment/migrations hcm/backend/recruitment/tests.py
git commit -m "recruitment: backfill historical closed/filled requisitions' positions"
```

---

### Task 9: Frontend — types, Positions page, nav/route wiring

**Files:**
- Modify: `hcm/frontend/src/api/types.ts`
- Create: `hcm/frontend/src/pages/PositionsPage.tsx`
- Modify: `hcm/frontend/src/layout/navConfig.ts`
- Modify: `hcm/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET/POST /api/v1/positions/`, `POST /api/v1/positions/{id}/submit/`, `.../decide/`, `.../revise/`
  (Task 3); `api.get`/`api.post` from `../api/client`; `useAllPages` from `../api/hooks`; `useAuth` from
  `../auth/AuthContext`.
- Produces: `PositionsPage` component, `/positions` route, nav entry.

- [ ] **Step 1: Add the TypeScript types**

```typescript
// hcm/frontend/src/api/types.ts -- add near the Requisition interface
export type PositionStatus = 'draft' | 'in_review' | 'approved' | 'rejected'

export interface PositionApprovalStep {
  id: number
  step_index: number
  role: string
  actor: number | null
  decision: 'approved' | 'rejected'
  comment: string
  created_at: string
}

export interface Position {
  id: number
  post_number: string
  title: string
  department: number
  occupational_level: number
  job_grade: number | null
  location: number
  status: PositionStatus
  current_step: number
  proposed_by: number | null
  approval_steps: PositionApprovalStep[]
  is_vacant: boolean
  current_incumbent_number: string | null
}

export const POSITION_STATUS_LABELS: Record<PositionStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  rejected: 'Rejected',
}
```

Also update the existing `Requisition` interface to add the new field:

```typescript
// hcm/frontend/src/api/types.ts -- Requisition interface, add positions: number[]
export interface Requisition {
  id: number
  title: string
  department: number
  occupational_level: number
  job_grade: number | null
  location: number
  headcount: number
  status: RequisitionStatus
  positions: number[]
  hiring_manager: number | null
  created_by: number | null
  opened_at: string | null
  target_fill_date: string | null
  closed_at: string | null
}
```

- [ ] **Step 2: Write `PositionsPage.tsx`**

This mirrors `EEReportsPage.tsx`'s structure (list + summary stats + propose form + per-row action buttons that
render only for whoever's role matches the position's current step).

```typescript
// hcm/frontend/src/pages/PositionsPage.tsx
import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import { POSITION_STATUS_LABELS, type Position, type PositionStatus } from '../api/types'
import { useAuth } from '../auth/AuthContext'

const APPROVAL_CHAIN_ROLES = ['comp_manager', 'accounting_officer'] as const

export function PositionsPage() {
  const { hasRole } = useAuth()
  const { data: positions, error: loadError, reload: load } = useAllPages<Position>('/positions/', [], 'Failed to load positions.')
  const [showForm, setShowForm] = useState(false)

  const canPropose = hasRole('hr_admin')
  const approvedCount = positions?.filter((p) => p.status === 'approved').length ?? 0
  const filledCount = positions?.filter((p) => p.status === 'approved' && !p.is_vacant).length ?? 0
  const vacantCount = approvedCount - filledCount
  const vacancyRate = approvedCount > 0 ? Math.round((vacantCount / approvedCount) * 1000) / 10 : 0

  return (
    <div className="page">
      <div className="page-header">
        <h1>Positions</h1>
        {canPropose && (
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Propose position'}
          </button>
        )}
      </div>

      {positions && (
        <p className="hint-text">
          {approvedCount} approved · {filledCount} filled · {vacantCount} vacant · {vacancyRate}% vacancy rate
        </p>
      )}

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && <ProposePositionForm onCreated={() => { setShowForm(false); load() }} />}

      {positions === null ? (
        <p className="empty-state">Loading…</p>
      ) : positions.length === 0 ? (
        <p className="empty-state">No positions yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Title</th>
                <th>Status</th>
                <th>Incumbent</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <PositionRow key={position.id} position={position} onChanged={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PositionRow({ position, onChanged }: { position: Position; onChanged: () => void }) {
  const { hasRole } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function act(action: string, body?: Record<string, unknown>) {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/positions/${position.id}/${action}/`, body)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  const requiredRole = position.status === 'in_review' ? APPROVAL_CHAIN_ROLES[position.current_step] : null

  return (
    <tr>
      <td>{position.post_number}</td>
      <td>{position.title}</td>
      <td>
        <span className="status-badge">{POSITION_STATUS_LABELS[position.status]}</span>
      </td>
      <td>{position.current_incumbent_number ?? (position.status === 'approved' ? 'Vacant' : '—')}</td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions">
          {position.status === 'draft' && hasRole('hr_admin') && (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('submit')}>
              Submit
            </button>
          )}
          {requiredRole && hasRole(requiredRole) && (
            <>
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('decide', { decision: 'approved' })}>
                Approve
              </button>
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('decide', { decision: 'rejected' })}>
                Reject
              </button>
            </>
          )}
          {position.status === 'rejected' && hasRole('hr_admin') && (
            <button type="button" className="btn-link" disabled={busy} onClick={() => void act('revise', {})}>
              Revise &amp; resubmit
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

function ProposePositionForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState<number | ''>('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [location, setLocation] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!department || !occupationalLevel || !location) {
      setError('Department, occupational level, and location are required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/positions/', {
        title, department, occupational_level: occupationalLevel, job_grade: jobGrade || null, location,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Propose failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Department
        <select value={department} onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.departmentList.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>
      <label>
        Occupational level
        <select value={occupationalLevel} onChange={(e) => setOccupationalLevel(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.occupationalLevelList.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </label>
      <label>
        Job grade
        <select value={jobGrade} onChange={(e) => setJobGrade(e.target.value ? Number(e.target.value) : '')}>
          <option value="">— None —</option>
          {ref.jobGradeList.filter((g) => g.occupational_level === occupationalLevel).map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
      </label>
      <label>
        Location
        <select value={location} onChange={(e) => setLocation(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.locationList.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Proposing…' : 'Propose position'}
        </button>
      </div>
    </form>
  )
}
```

Note: `hasRole(requiredRole)` compiles as-is — `AuthContext.tsx`'s `hasRole` is typed `(role: string) => boolean`,
already accepting a plain string, not narrowed to a literal union. No cast needed.

- [ ] **Step 3: Wire the route and nav entry**

```typescript
// hcm/frontend/src/layout/navConfig.ts -- add role group and entry
const ESTABLISHMENT = ['hr_admin', 'comp_manager', 'accounting_officer', 'auditor', 'recruiter'] as const

export const NAV_ITEMS: readonly NavItem[] = [
  ...
  { to: '/requisitions', label: 'Requisitions', roles: RECRUIT },
  { to: '/positions', label: 'Positions', roles: ESTABLISHMENT },
  ...
]
```

```typescript
// hcm/frontend/src/App.tsx -- add import and route
import { PositionsPage } from './pages/PositionsPage'
...
              <Route path="/positions" element={<PositionsPage />} />
```

- [ ] **Step 4: Typecheck, lint, build**

Run: `cd hcm/frontend && npx tsc -b && npm run lint && npm run build`
Expected: all clean. Fix any type errors (most likely the `hasRole(requiredRole)` call from Step 2's note) before
continuing.

- [ ] **Step 5: Commit**

```bash
git add hcm/frontend/src/api/types.ts hcm/frontend/src/pages/PositionsPage.tsx hcm/frontend/src/layout/navConfig.ts hcm/frontend/src/App.tsx
git commit -m "frontend: Positions page (propose/submit/decide/revise, vacancy stats)"
```

---

### Task 10: Frontend — multi-select position picker on the requisition form

**Files:**
- Modify: `hcm/frontend/src/pages/RequisitionsPage.tsx`

**Interfaces:**
- Consumes: `GET /positions/?vacant=true` (Task 3's `vacant` query param), `Position` type (Task 9).

- [ ] **Step 1: Add the multi-select picker to `NewRequisitionForm`**

```typescript
// hcm/frontend/src/pages/RequisitionsPage.tsx -- add imports
import { useAllPages } from '../api/hooks'
import { type Position } from '../api/types'

// inside NewRequisitionForm, add state and a fetch of vacant positions filtered to the chosen dept/level/grade:
function NewRequisitionForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState<number | ''>('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [location, setLocation] = useState<number | ''>('')
  const [headcount, setHeadcount] = useState(1)
  const [status, setStatus] = useState<RequisitionStatus>('open')
  const [selectedPositions, setSelectedPositions] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const { data: vacantPositions } = useAllPages<Position>('/positions/?vacant=true', [], 'Failed to load positions.')
  const candidatePositions = (vacantPositions ?? []).filter(
    (p) => p.department === department && p.occupational_level === occupationalLevel
      && (jobGrade === '' || p.job_grade === jobGrade),
  )

  function togglePosition(id: number) {
    setSelectedPositions((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!department || !occupationalLevel || !location) {
      setError('Department, occupational level, and location are required.')
      return
    }
    if (selectedPositions.length !== headcount) {
      setError(`Select exactly ${headcount} approved, vacant position(s) to match headcount.`)
      return
    }
    setSubmitting(true)
    try {
      await api.post('/requisitions/', {
        title, department, occupational_level: occupationalLevel, job_grade: jobGrade || null, location,
        headcount, status, positions: selectedPositions,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }
```

Add the picker UI, right after the existing "Headcount" label block:

```typescript
      <label>
        Headcount
        <input type="number" min={1} value={headcount} onChange={(e) => setHeadcount(Number(e.target.value))} />
      </label>
      <fieldset>
        <legend>Positions ({selectedPositions.length} of {headcount} selected)</legend>
        {candidatePositions.length === 0 ? (
          <p className="hint-text">No approved, vacant positions match this department/level/grade yet.</p>
        ) : (
          candidatePositions.map((p) => (
            <label key={p.id} style={{ display: 'block' }}>
              <input
                type="checkbox"
                checked={selectedPositions.includes(p.id)}
                onChange={() => togglePosition(p.id)}
              />
              {p.post_number} — {p.title}
            </label>
          ))
        )}
      </fieldset>
```

(The closing `</form>` and rest of the component are unchanged — only the field list and submit handler above
change.)

- [ ] **Step 2: Typecheck, lint, build**

Run: `cd hcm/frontend && npx tsc -b && npm run lint && npm run build`
Expected: clean.

- [ ] **Step 3: Manual browser smoke check**

This is a UI change — per this project's own convention, verify it in a real browser before considering the task
done (see `docs/superpowers/plans` sibling tasks' precedent and `hcm/README.md`'s dev-server instructions): start
the backend (`python manage.py runserver`) and frontend (`npm run dev`) dev servers, log in as `hradmin`, propose
and fully approve one Position (as `hradmin`/`compmanager`/`accountingofficer` in turn), then log in as `recruiter`
and confirm the approved position appears in the new requisition form's picker and the requisition creates
successfully. This corresponds to the spec's §7 "browser-verified" scenario — Task 11's e2e test automates this
same path, but a manual pass here catches anything the e2e test's exact selectors might miss.

- [ ] **Step 4: Commit**

```bash
git add hcm/frontend/src/pages/RequisitionsPage.tsx
git commit -m "frontend: multi-select vacant-position picker on the requisition form"
```

---

### Task 11: End-to-end browser test

**Files:**
- Create: `hcm/frontend/e2e/establishment.spec.ts`
- Modify: `hcm/backend/core_hr/management/commands/seed_demo_data.py`

**Interfaces:**
- Consumes: `e2e/helpers.ts` (`login`, `expectHeading`, `settled`), demo logins (`hradmin`, `compmanager`,
  `accountingofficer`, `recruiter` — confirm `recruiter` is already a seeded demo login; if not, this task adds one,
  matching the pattern every other role login already follows in `seed_demo_data.py`).

- [ ] **Step 0: Confirm a `recruiter` demo login exists**

Run: `grep -n "recruiter" hcm/backend/core_hr/management/commands/seed_demo_data.py`
If a `recruiter`/`recruiter123` login already exists (likely, given `recruitment` shipped in Sprint 4-5), skip
straight to Step 1. If not, add one following the exact pattern the other role logins use in that file (same
`Employee.objects.hire(..., user=User.objects.create_user(username="recruiter", password="recruiter123"))` +
`RoleAssignment.objects.create(..., role=Role.objects.get(name="recruiter"))` shape).

- [ ] **Step 1: Write the e2e test**

```typescript
// hcm/frontend/e2e/establishment.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Position / establishment management (C1)', () => {
  test('propose -> comp_manager approves -> accounting_officer approves -> recruiter sees it in the requisition picker', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/positions')
    await expectHeading(page, 'Positions')
    await settled(page)

    await page.getByRole('button', { name: '+ Propose position' }).click()
    await page.getByLabel('Title').fill('E2E Test Post')
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await page.getByLabel('Location').selectOption({ index: 1 })
    await page.getByRole('button', { name: 'Propose position' }).click()
    await settled(page)

    const row = page.locator('tr', { hasText: 'E2E Test Post' })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Submit' }).click()
    await settled(page)
    await expect(row).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'compmanager')
    await page.goto('/positions')
    await settled(page)
    const compRow = page.locator('tr', { hasText: 'E2E Test Post' })
    await compRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(compRow).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'accountingofficer')
    await page.goto('/positions')
    await settled(page)
    const aoRow = page.locator('tr', { hasText: 'E2E Test Post' })
    await aoRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(aoRow).toContainText('Approved')
    await expect(aoRow).toContainText('Vacant')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'recruiter')
    await page.goto('/requisitions')
    await expectHeading(page, 'Requisitions')
    await page.getByRole('button', { name: '+ New requisition' }).click()
    // the picker is filtered to the form's currently-selected department/
    // level (empty until chosen) -- select the SAME ones used to propose
    // the position above (also index 1) before its post_number can appear.
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await expect(page.getByText('E2E Test Post', { exact: false })).toBeVisible()
  })

  test('a plain employee cannot reach the Positions page', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/positions')
    await page.waitForURL(/\/employees$/)
  })
})
```

- [ ] **Step 2: Run the e2e test**

Run: `cd hcm/frontend && npx playwright test establishment.spec.ts`
Expected: both tests PASS. If the department/occupational-level `selectOption({ index: 1 })` picks a combination
with no seeded `JobGrade`, the propose form's job-grade selector staying empty is fine (it's optional) — but if the
department/level combination somehow makes the picker page (Step 1's last assertions) fail to find the position,
switch to selecting a specific known department/level by label text instead of index (check `ReferenceDataContext`
seed values in `seed_demo_data.py` for a department name guaranteed to exist, e.g. `"Engineering"`).

- [ ] **Step 3: Run the full e2e suite**

Run: `cd hcm/frontend && npm test`
Expected: full suite green, no regressions from the `Requisition.positions` requirement breaking any *other*
existing e2e spec that creates a requisition without positions (grep `e2e/*.spec.ts` for any `POST /requisitions/`
or a "New requisition" form submission in another spec file before this step — if one exists, it needs positions
added the same way Task 10 does, or it will now fail).

- [ ] **Step 4: Commit**

```bash
git add hcm/frontend/e2e/establishment.spec.ts hcm/backend/core_hr/management/commands/seed_demo_data.py
git commit -m "e2e: Position approval chain + requisition picker browser test"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage**: §2 (Task 1, 2), §3 backfill (Task 5), §4.1 (Task 4), §4.2/§4.3 (Task 6, 7), §4.4 (no code —
  confirmed derived, no task needed), §5 access (Task 3), §6 frontend (Task 9, 10), §7 testing (spread across every
  task's own test steps + Task 11's e2e), §8 rollout ordering (Tasks 1→8 backend, then 9→11 frontend, matches).
  §9 (flexibility boundaries) is documentation or a deliberate future non-goal, not implementation — no task needed.
- **Real bug caught while planning, not in the original spec**: `RequisitionSerializer.validate` naively
  re-checking every linked position's vacancy on every save would incorrectly reject an unrelated later PATCH to a
  requisition once one of its own linked positions gets filled by its own hire. Task 6's
  `validate_requisition_positions` exempts already-linked positions from the strict checks — proven by
  `test_already_linked_position_is_allowed_even_once_filled`.
- **Second pass caught two more issues, both fixed in place**: (1) Task 11's e2e test originally checked the
  requisition form's position picker for visibility before selecting a department/occupational level on that form —
  the picker is filtered to the form's own selection state, so the position could never actually appear; fixed by
  selecting the same department/level used to propose the position first. (2) Several test-code blocks (Tasks 4, 6,
  7) redefined or re-imported things (`_seed_reference_data`, `Employee`, `Applicant`, `transition_applicant`,
  `EmployeeVersion`) that the real, already-existing `recruitment/tests.py` and `core_hr/tests.py` files import or
  define at module level — confirmed directly against those files and trimmed to only genuinely new imports.
- **Known follow-up not in this plan** (correctly out of scope per the spec's own non-goals): editing an
  already-`approved` Position's establishment-defining fields, an `on_hold`/`abolished` status, and any runtime
  chain-editing UI — all explicitly deferred, see spec §9.
