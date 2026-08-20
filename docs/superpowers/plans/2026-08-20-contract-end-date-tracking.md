# Contract End-Date Tracking & Renewal Decisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track fixed-term employees' contract end dates, remind their manager (then hr_admin, on escalation) as the date approaches, and let a manager-recommends/hr_admin-decides workflow renew, convert to permanent, or let the contract lapse.

**Architecture:** Extends `core_hr` directly (no new app) — a new `contract_end_date` field on `EmployeeVersion`, a new `ContractRenewalDecision` model recording the recommend/decide workflow, two service functions (`core_hr/contracts.py`) that call the existing `Employee.apply_lifecycle_event()` to execute a decision, a daily Celery task mirroring PC-1's reminder shape, and `recommend_contract`/`decide_contract` actions added directly to the existing `EmployeeVersionViewSet` (mirroring `EmployeeViewSet.consent`/`self_identify`'s established shape, rather than a new parallel ViewSet).

**Tech Stack:** Django 5.2 + DRF (`hcm/backend`), React 19 + TypeScript + Vite (`hcm/frontend`), Celery, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-20-contract-end-date-tracking-design.md`

**Note on this plan vs. the spec:** the spec's §4/§6/§9 describe a `ContractPermission` class and implied a possible dedicated ViewSet. Research during plan-writing found `rbac_audit.drf.RowScopePermission` + `row_scoped_queryset()` already solves exactly this "manager sees own reports, hr_admin/auditor see all" shape generically (it's what `EmployeeVersionViewSet` itself already uses) — and `EmployeeViewSet.consent`/`self_identify` already establish the exact pattern for "existing resource gains a POST action with its own inline role check" that `recommend`/`decide` need. This plan uses both rather than inventing new parallel machinery. **Zero behavior change from the spec** — same access rules, same actions, same data; only the implementation mechanism is more consistent with what's already here.

## Global Constraints

- Direct-to-master execution (no worktree/branch) — matches this session's established convention for the whole HR_system project.
- GitHub Actions CI is currently billing-blocked (account-level, not code) — run real local test suites for verification, then commit and push directly; don't wait on or gate on CI status.
- `recommend_contract_action`/`decide_contract_action` (Task 2) contain **no role/permission checks** — those belong in the view layer (Task 3), matching the established 403-vs-400 split used throughout this codebase (wrong role → 403 in the view; wrong state → 400 from the service raising a domain error).
- `contract_end_date` **is** in `VERSION_CARRY_FIELDS` (carries forward on unrelated version changes like promotions) — the two decision-execution paths (RENEW, CONVERT_PERMANENT) explicitly override it via `apply_lifecycle_event`'s `field_updates`, which take priority over the carried-forward default.
- No backfill migration for existing fixed-term employees missing a `contract_end_date` — surfaced via the data-quality registry instead (Task 1), cleared through Django admin.
- Role name string for the manager role is exactly `"line_manager"` (confirmed in `seed_demo_data.py`) — not `"manager"` (that's the demo login *username*, a different thing).

---

### Task 1: Data model — `contract_end_date`, `ContractRenewalDecision`, new choices, tiers, admin

**Files:**
- Modify: `hcm/backend/core_hr/models.py:179-184` (`VERSION_CARRY_FIELDS`), `:277-386` (`EmployeeVersion`), `:389-396` (`EmploymentEvent.EventType`), `:429-441` (`DataQualityException.ExceptionType`)
- Modify: `hcm/backend/core_hr/data_quality.py:70-98` (`_builtin_core_hr_checks`)
- Modify: `hcm/backend/rbac_audit/tiers.py` (add `contract_end_date` to the existing `"core_hr.EmployeeVersion"` entry, add a new `"core_hr.ContractRenewalDecision"` entry)
- Modify: `hcm/backend/core_hr/admin.py` (`EmployeeVersionInline.fields`, register `ContractRenewalDecisionAdmin`)
- Create: migration (via `makemigrations`, verify the generated file)
- Test: `hcm/backend/core_hr/tests.py`

**Interfaces:**
- Produces: `EmployeeVersion.contract_end_date` (nullable `DateField`), `ContractRenewalDecision` model (fields exactly as in spec §3.2 — `employee_version`, `status`, `recommended_action`/`recommended_by`/`recommended_at`/`recommended_comment`/`recommended_end_date`, `decided_action`/`decided_by`/`decided_at`/`decided_comment`/`decided_end_date`, `resulting_employee_version`), `EmploymentEvent.EventType.CONTRACT_RENEWAL`, `DataQualityException.ExceptionType.MISSING_CONTRACT_END_DATE`.

- [ ] **Step 1: Write the failing tests**

Add to `hcm/backend/core_hr/tests.py` (append near the other `EmployeeVersion`/`EmploymentEvent`-related tests — check the file's existing test-class layout and match its fixture style, e.g. reuse whatever `setUp()` already builds a `Department`/`OccupationalLevel`/`Location`/hired `Employee`):

```python
class ContractEndDateFieldTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=3)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31),
        )

    def test_contract_end_date_stored_on_hire(self):
        self.assertEqual(self.employee.current_version.contract_end_date, date(2026, 12, 31))

    def test_contract_end_date_carries_forward_on_unrelated_promotion(self):
        self.employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.PROMOTION, effective_date=date(2026, 6, 1),
            job_title="Senior Contractor",
        )
        self.assertEqual(self.employee.current_version.contract_end_date, date(2026, 12, 31))

    def test_contract_end_date_null_for_permanent_employee(self):
        permanent = Employee.objects.hire(
            employee_number="E901", first_name="Test", last_name="Permanent",
            date_of_birth=date(1990, 1, 1), work_email="permanent@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.assertIsNone(permanent.current_version.contract_end_date)


class ContractRenewalDecisionModelTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=3)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor2@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31), manager=self.manager,
        )

    def test_one_decision_row_per_version(self):
        version = self.employee.current_version
        ContractRenewalDecision.objects.create(employee_version=version, status=ContractRenewalDecision.Status.RECOMMENDED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContractRenewalDecision.objects.create(employee_version=version, status=ContractRenewalDecision.Status.RECOMMENDED)

    def test_no_row_created_by_default(self):
        self.assertFalse(ContractRenewalDecision.objects.filter(employee_version=self.employee.current_version).exists())
```

Add the necessary imports at the top of `tests.py` if not already present: `from django.db import IntegrityError, transaction`, `EmploymentEvent`, and the new `ContractRenewalDecision` (check the file's current import block — extend it, don't duplicate an existing `from .models import (...)` line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test core_hr.tests.ContractEndDateFieldTests core_hr.tests.ContractRenewalDecisionModelTests -v 2`
Expected: FAIL — `Employee.objects.hire()` doesn't accept `contract_end_date`, `ContractRenewalDecision` doesn't exist.

- [ ] **Step 3: `VERSION_CARRY_FIELDS` + `EmployeeVersion.contract_end_date`**

In `hcm/backend/core_hr/models.py`, add `"contract_end_date"` to `VERSION_CARRY_FIELDS` (line 179-184):

```python
VERSION_CARRY_FIELDS = (
    "department", "job_title", "occupational_level", "job_grade", "manager",
    "employment_status", "citizenship_status", "location", "position",
    "contract_end_date",
    "race", "gender", "disability_status", "disability_detail",
    "race_source", "disability_source",
)
```

Add the field to `EmployeeVersion`, immediately after the `position` field (after line 341, before the blank line preceding `race`):

```python
    # Meaningful only when employment_status == FIXED_TERM. Nullable by
    # design (no forced backfill for existing fixed-term employees — see
    # data_quality.py's MISSING_CONTRACT_END_DATE check instead). IS in
    # VERSION_CARRY_FIELDS: an unrelated version change (e.g. a promotion)
    # must not silently wipe a still-active contract's end date.
    contract_end_date = models.DateField(null=True, blank=True)
```

- [ ] **Step 4: `Employee.objects.hire()` gains a `contract_end_date` kwarg**

`hire()` is defined on `EmployeeManager` (`core_hr/models.py`, above line 179 — read the current method signature first, it's not shown in this plan verbatim since it wasn't quoted during research; find it by searching for `def hire` in the file). Add a keyword-only `contract_end_date=None` parameter, threaded into the `EmployeeVersion.objects.create(...)` call the same way `position=None` already is (part 1 added that kwarg the same way — follow its exact pattern in this same method).

- [ ] **Step 5: `EmploymentEvent.EventType.CONTRACT_RENEWAL`**

In `EmploymentEvent.EventType` (line 390-396), add after `CONTRACT_CONVERSION`:

```python
    class EventType(models.TextChoices):
        HIRE = "hire", "Hire"
        PROMOTION = "promotion", "Promotion"
        TRANSFER = "transfer", "Transfer"
        GRADE_CHANGE = "grade_change", "Grade change"
        TERMINATION = "termination", "Termination"
        CONTRACT_CONVERSION = "contract_conversion", "Contract conversion"
        CONTRACT_RENEWAL = "contract_renewal", "Contract renewal"
```

(`TerminationReason.CONTRACT_END` already exists at line 405 — no change needed there.)

- [ ] **Step 6: `ContractRenewalDecision` model**

Add after the `EmploymentEvent` class (after line 427, before `class DataQualityException`):

```python
class ContractRenewalDecision(TimestampedModel):
    """One row per upcoming fixed-term contract expiry, created the moment
    someone (manager or hr_admin) first acts — there is no synthetic
    'pending, nothing happened yet' row. See design spec §3.2/§4."""

    class Status(models.TextChoices):
        RECOMMENDED = "recommended", "Recommended"
        DECIDED = "decided", "Decided"

    class Action(models.TextChoices):
        RENEW = "renew", "Renew"
        CONVERT_PERMANENT = "convert_permanent", "Convert to permanent"
        LET_LAPSE = "let_lapse", "Let lapse"

    employee_version = models.OneToOneField(
        EmployeeVersion, on_delete=models.CASCADE, related_name="contract_renewal_decision",
    )
    status = models.CharField(max_length=20, choices=Status.choices)

    recommended_action = models.CharField(max_length=20, choices=Action.choices, null=True, blank=True)
    recommended_by = models.ForeignKey(Employee, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    recommended_at = models.DateTimeField(null=True, blank=True)
    recommended_comment = models.TextField(blank=True)
    recommended_end_date = models.DateField(null=True, blank=True)

    decided_action = models.CharField(max_length=20, choices=Action.choices, null=True, blank=True)
    decided_by = models.ForeignKey(Employee, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_comment = models.TextField(blank=True)
    decided_end_date = models.DateField(null=True, blank=True)

    resulting_employee_version = models.ForeignKey(
        EmployeeVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.employee_version.employee.employee_number}: {self.status}"
```

(`TimestampedModel`/`HistoricalRecords` are already imported at the top of this file — match every other model's usage in it.)

- [ ] **Step 7: `DataQualityException.ExceptionType.MISSING_CONTRACT_END_DATE` + the check**

In `DataQualityException.ExceptionType` (line 430-433), add alongside the other **built-in** choices (not the H3-registered ones below the comment):

```python
    class ExceptionType(models.TextChoices):
        MISSING_GRADE = "missing_grade", "Missing job grade"
        MISSING_DEMOGRAPHICS = "missing_demographics", "Missing demographics"
        ORPHAN_RECORD = "orphan_record", "Orphan record (no version history)"
        MISSING_CONTRACT_END_DATE = "missing_contract_end_date", "Fixed-term employee missing contract end date"
        # H3: org-wide checks registered from other apps' AppConfig.ready()
        ...
```

In `hcm/backend/core_hr/data_quality.py`, add to `_builtin_core_hr_checks()` (inside the `for employee in Employee.objects.all():` loop, after the `missing_demo` block, before the function ends around line 98):

```python
        if current.employment_status == EmployeeVersion.EmploymentStatus.FIXED_TERM and current.contract_end_date is None:
            yield (
                employee, DataQualityException.ExceptionType.MISSING_CONTRACT_END_DATE,
                "Fixed-term employee has no contract end date recorded.",
            )
```

Add `EmployeeVersion` to `data_quality.py`'s imports (currently `from .models import DataQualityException, Employee` — extend it).

- [ ] **Step 8: `rbac_audit/tiers.py`**

Read the file's current `FIELD_TIERS` structure first (the `"core_hr.EmployeeVersion"` entry starts at line 39). Add `"contract_end_date": FieldTier.PUBLIC` to that entry (same tier as `position` — an end date is operational, not sensitive personal data). Add a new top-level entry for the new model:

```python
    "core_hr.ContractRenewalDecision": {
        "recommended_comment": FieldTier.INTERNAL,
        "decided_comment": FieldTier.INTERNAL,
    },
```

(Everything else on `ContractRenewalDecision` defaults to PUBLIC per this file's own default-tier convention — only override where a field genuinely needs a stricter tier. Confirm this default-tier assumption against the file's own header comment before committing to leaving the rest unlisted.)

- [ ] **Step 9: `core_hr/admin.py`**

Add `"contract_end_date"` to `EmployeeVersionInline.fields` (the tuple at line 20-23), and register the new model:

```python
@admin.register(ContractRenewalDecision)
class ContractRenewalDecisionAdmin(SimpleHistoryAdmin):
    list_display = ("employee_version", "status", "recommended_action", "decided_action")
    list_filter = ("status",)
    search_fields = ("employee_version__employee__employee_number",)
```

Add `ContractRenewalDecision` to this file's `from .models import (...)` line.

- [ ] **Step 10: Generate and verify the migration**

Run: `cd hcm/backend && python manage.py makemigrations core_hr`
Expected: one new migration file. Open it and confirm it contains: the `contract_end_date` field addition, the `VERSION_CARRY_FIELDS`-related no-op (there's no DB representation of that tuple, so nothing to verify there beyond the field itself), the `ContractRenewalDecision` table (with its historical-records shadow table, matching every other `HistoricalRecords()` model in this file), the `EventType`/`ExceptionType` choices alterations (options-only, no schema change — same shape as `core_hr/migrations/0007_employeeversion_one_current_occupant_per_position.py`'s sibling option-only migrations from C1 part 1).

- [ ] **Step 11: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test core_hr.tests.ContractEndDateFieldTests core_hr.tests.ContractRenewalDecisionModelTests -v 2`
Expected: PASS.

- [ ] **Step 12: Run the full core_hr suite + system checks**

Run: `cd hcm/backend && python manage.py test core_hr -v 2 && python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: all pass, no pending migrations.

- [ ] **Step 13: Commit**

```bash
git add hcm/backend/core_hr/models.py hcm/backend/core_hr/data_quality.py hcm/backend/core_hr/admin.py hcm/backend/core_hr/tests.py hcm/backend/core_hr/migrations/ hcm/backend/rbac_audit/tiers.py
git commit -m "core_hr: contract_end_date field + ContractRenewalDecision model"
```

---

### Task 2: Service layer — `recommend_contract_action` / `decide_contract_action`

**Files:**
- Create: `hcm/backend/core_hr/contracts.py`
- Test: `hcm/backend/core_hr/tests.py` (new test class, same file as Task 1's model tests)

**Interfaces:**
- Consumes: `ContractRenewalDecision`, `EmployeeVersion`, `EmploymentEvent`, `Employee.apply_lifecycle_event()` (Task 1).
- Produces: `recommend_contract_action(employee_version, *, actor, action, comment="", end_date=None) -> ContractRenewalDecision`, `decide_contract_action(employee_version, *, actor, action, comment="", end_date=None) -> ContractRenewalDecision`, both raising `ContractDecisionError(ValueError)` on state-machine violations (Task 3's view layer catches this the same way `establishment.services.ApprovalError` is caught in `establishment/views.py`).

- [ ] **Step 1: Write the failing tests**

Append to `hcm/backend/core_hr/tests.py`:

```python
class ContractDecisionServiceTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=3)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager3@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.hr_admin = Employee.objects.hire(
            employee_number="E801", first_name="HR", last_name="Admin",
            date_of_birth=date(1980, 1, 1), work_email="hradmin3@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor3@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31), manager=self.manager,
        )
        self.version = self.employee.current_version

    def test_recommend_creates_a_recommended_row(self):
        decision = recommend_contract_action(
            self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW,
            comment="Team still needs them.", end_date=date(2027, 12, 31),
        )
        self.assertEqual(decision.status, ContractRenewalDecision.Status.RECOMMENDED)
        self.assertEqual(decision.recommended_by, self.manager)
        self.assertEqual(decision.recommended_end_date, date(2027, 12, 31))

    def test_recommend_twice_raises(self):
        recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 12, 31))
        with self.assertRaises(ContractDecisionError):
            recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.LET_LAPSE)

    def test_decide_without_a_prior_recommendation_is_allowed(self):
        decision = decide_contract_action(
            self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT,
        )
        self.assertEqual(decision.status, ContractRenewalDecision.Status.DECIDED)
        self.assertIsNone(decision.recommended_action)

    def test_decide_renew_creates_a_new_version_and_closes_the_old_one(self):
        decide_contract_action(
            self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.RENEW,
            end_date=date(2027, 12, 31),
        )
        self.version.refresh_from_db()
        self.assertIsNotNone(self.version.valid_to)
        new_version = self.employee.current_version
        self.assertEqual(new_version.contract_end_date, date(2027, 12, 31))
        self.assertEqual(new_version.employment_status, EmployeeVersion.EmploymentStatus.FIXED_TERM)
        decision = ContractRenewalDecision.objects.get(employee_version=self.version)
        self.assertEqual(decision.resulting_employee_version, new_version)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.CONTRACT_RENEWAL)

    def test_decide_convert_permanent_clears_the_end_date(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT)
        new_version = self.employee.current_version
        self.assertEqual(new_version.employment_status, EmployeeVersion.EmploymentStatus.PERMANENT)
        self.assertIsNone(new_version.contract_end_date)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.CONTRACT_CONVERSION)

    def test_decide_let_lapse_terminates_with_no_new_version(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.LET_LAPSE)
        self.assertIsNone(self.employee.current_version)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.TERMINATION)
        self.assertEqual(event.termination_reason, EmploymentEvent.TerminationReason.CONTRACT_END)
        decision = ContractRenewalDecision.objects.get(employee_version=self.version)
        self.assertIsNone(decision.resulting_employee_version)

    def test_decide_twice_raises(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT)
        with self.assertRaises(ContractDecisionError):
            decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.LET_LAPSE)

    def test_decide_accepts_and_can_override_a_recommendation(self):
        recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 6, 30))
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 12, 31))
        new_version = self.employee.current_version
        self.assertEqual(new_version.contract_end_date, date(2027, 12, 31))
```

Add the new imports: `from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test core_hr.tests.ContractDecisionServiceTests -v 2`
Expected: FAIL — `core_hr.contracts` doesn't exist.

- [ ] **Step 3: Implement `core_hr/contracts.py`**

```python
"""Service layer for the contract end-date renewal workflow (C1 part 2).
No role/permission checks here — those belong in the view layer
(EmployeeVersionViewSet.recommend_contract/decide_contract), matching
this codebase's established 403-vs-400 split: wrong role is a view-layer
403, wrong state is a service-layer ContractDecisionError -> 400."""
from __future__ import annotations

from django.utils import timezone

from .models import ContractRenewalDecision, EmployeeVersion, EmploymentEvent


class ContractDecisionError(ValueError):
    """Raised for state-machine violations (re-recommending, re-deciding)."""


def recommend_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    if hasattr(employee_version, "contract_renewal_decision"):
        raise ContractDecisionError("A decision already exists for this contract.")
    if action == ContractRenewalDecision.Action.RENEW and end_date is None:
        raise ContractDecisionError("end_date is required when recommending a renewal.")
    return ContractRenewalDecision.objects.create(
        employee_version=employee_version,
        status=ContractRenewalDecision.Status.RECOMMENDED,
        recommended_action=action,
        recommended_by=actor,
        recommended_at=timezone.now(),
        recommended_comment=comment,
        recommended_end_date=end_date if action == ContractRenewalDecision.Action.RENEW else None,
    )


def decide_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    if action == ContractRenewalDecision.Action.RENEW and end_date is None:
        raise ContractDecisionError("end_date is required when deciding to renew.")

    decision, _ = ContractRenewalDecision.objects.get_or_create(
        employee_version=employee_version,
        defaults={"status": ContractRenewalDecision.Status.RECOMMENDED},
    )
    if decision.status == ContractRenewalDecision.Status.DECIDED:
        raise ContractDecisionError("This contract's decision has already been made.")

    decision.status = ContractRenewalDecision.Status.DECIDED
    decision.decided_action = action
    decision.decided_by = actor
    decision.decided_at = timezone.now()
    decision.decided_comment = comment
    decision.decided_end_date = end_date if action == ContractRenewalDecision.Action.RENEW else None

    employee = employee_version.employee
    effective_date = decision.decided_at.date()

    if action == ContractRenewalDecision.Action.RENEW:
        event = employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.CONTRACT_RENEWAL, effective_date=effective_date,
            contract_end_date=end_date,
        )
        decision.resulting_employee_version = event.to_version
    elif action == ContractRenewalDecision.Action.CONVERT_PERMANENT:
        event = employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.CONTRACT_CONVERSION, effective_date=effective_date,
            employment_status=EmployeeVersion.EmploymentStatus.PERMANENT, contract_end_date=None,
        )
        decision.resulting_employee_version = event.to_version
    elif action == ContractRenewalDecision.Action.LET_LAPSE:
        employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TERMINATION, effective_date=effective_date,
            termination_reason=EmploymentEvent.TerminationReason.CONTRACT_END,
        )
    else:
        raise ContractDecisionError(f"'{action}' is not a valid decision action.")

    decision.save()
    return decision
```

Note: `hasattr(employee_version, "contract_renewal_decision")` is the standard Django idiom for "does this OneToOne reverse relation exist" — it triggers the descriptor, which raises `ObjectDoesNotExist` internally on a cache miss with no row, and `hasattr` swallows that specific exception (Python 3's `hasattr` only swallows `AttributeError` by default, but Django's related-object descriptors are implemented to raise `ObjectDoesNotExist`, and Django's own codebase — and this project's own OneToOne usage patterns elsewhere, e.g. `Employee.user`, — rely on this idiom too; confirm this works as expected via Step 4's test run rather than taking it on faith).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test core_hr.tests.ContractDecisionServiceTests -v 2`
Expected: PASS. If `hasattr(...)` doesn't behave as described above, replace it with an explicit `try: employee_version.contract_renewal_decision; raise ContractDecisionError(...) except ContractRenewalDecision.DoesNotExist: pass` and note the deviation in your report.

- [ ] **Step 5: Run the full core_hr suite**

Run: `cd hcm/backend && python manage.py test core_hr -v 2`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hcm/backend/core_hr/contracts.py hcm/backend/core_hr/tests.py
git commit -m "core_hr: recommend/decide contract action services"
```

---

### Task 3: API layer — `recommend_contract`/`decide_contract` actions, serializer fields, `?fixed_term=true`

**Files:**
- Modify: `hcm/backend/core_hr/serializers.py` (`EmployeeVersionSerializer`, new `ContractRenewalDecisionSerializer`)
- Modify: `hcm/backend/core_hr/views.py` (`EmployeeVersionViewSet`)
- Test: `hcm/backend/core_hr/test_api.py`

**Interfaces:**
- Consumes: `recommend_contract_action`/`decide_contract_action`/`ContractDecisionError` (Task 2).
- Produces: `GET /api/v1/employee-versions/?fixed_term=true` (combine with existing `?current=true`), `POST /api/v1/employee-versions/{id}/recommend_contract/`, `POST /api/v1/employee-versions/{id}/decide_contract/`. `EmployeeVersionSerializer` output gains a `contract_end_date` field and a nested `contract_renewal_decision` (null if none exists yet).

- [ ] **Step 1: Write the failing tests**

Append to `hcm/backend/core_hr/test_api.py` (match the file's existing `APIClient`/fixture-setup style — read its current `setUp()`/base test-case class first):

```python
class ContractActionApiTests(EmployeeApiTestCase):  # match whatever base class test_api.py's other tests use
    def setUp(self):
        super().setUp()
        self.employee.current_version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        self.employee.current_version.contract_end_date = date(2026, 12, 31)
        self.employee.current_version.manager = self.manager  # ensure a manager fixture exists in setUp(); if not, hire one here
        self.employee.current_version.save()

    def test_manager_can_recommend_for_own_report(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "recommended")

    def test_non_manager_cannot_recommend(self):
        self.client.force_authenticate(user=self.employee.user or self.other_employee.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_decide(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "decided")

    def test_manager_cannot_decide(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_deciding_twice_is_400_not_500(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "let_lapse"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_fixed_term_filter(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/employee-versions/?fixed_term=true&current=true")
        self.assertEqual(response.status_code, 200)
        returned_ids = {v["id"] for v in response.data["results"]} if "results" in response.data else {v["id"] for v in response.data}
        self.assertIn(self.employee.current_version.id, returned_ids)

    def test_serializer_includes_null_decision_before_any_action(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/employee-versions/{self.employee.current_version.id}/")
        self.assertIsNone(response.data["contract_renewal_decision"])
```

**Before writing this step for real:** read `core_hr/test_api.py`'s actual current top-of-file fixtures (base test case, what `self.manager`/`self.hr_admin`/`self.employee` already look like, how role assignment and `force_authenticate` are done elsewhere in that file) and adjust the test class above to match exactly — the shape above is illustrative of *what* to cover, not a guaranteed drop-in (this plan's research did not open `test_api.py`'s full contents).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hcm/backend && python manage.py test core_hr.test_api.ContractActionApiTests -v 2`
Expected: FAIL — the actions/fields/filter don't exist yet.

- [ ] **Step 3: Serializers**

In `hcm/backend/core_hr/serializers.py`, add a new serializer and extend `EmployeeVersionSerializer`:

```python
class ContractRenewalDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractRenewalDecision
        fields = [
            "id", "status",
            "recommended_action", "recommended_by", "recommended_at", "recommended_comment", "recommended_end_date",
            "decided_action", "decided_by", "decided_at", "decided_comment", "decided_end_date",
            "resulting_employee_version",
        ]
```

```python
class EmployeeVersionSerializer(TieredModelSerializer):
    contract_renewal_decision = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeVersion
        fields = [
            "id", "employee", "valid_from", "valid_to", "department", "job_title",
            "occupational_level", "job_grade", "manager", "employment_status",
            "citizenship_status", "location", "contract_end_date", "contract_renewal_decision",
            "race", "gender", "disability_status", "disability_detail", "race_source", "disability_source",
        ]

    def get_contract_renewal_decision(self, obj):
        try:
            return ContractRenewalDecisionSerializer(obj.contract_renewal_decision).data
        except ContractRenewalDecision.DoesNotExist:
            return None
```

Add `ContractRenewalDecision` to this file's `from .models import (...)` block.

- [ ] **Step 4: View actions + filter**

In `hcm/backend/core_hr/views.py`:

Add `?fixed_term=true` to `EmployeeVersionViewSet.get_queryset()` (after the existing `?current=true` handling, around line 51):

```python
        if self.request.query_params.get("fixed_term") == "true":
            queryset = queryset.filter(
                employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
                contract_end_date__isnull=False,
            )
```

Add two actions to `EmployeeVersionViewSet` (after `get_target_employee`, matching `EmployeeViewSet.consent`/`self_identify`'s exact inline-role-check shape):

```python
    @action(detail=True, methods=["post"])
    def recommend_contract(self, request, pk=None):
        version = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not has_role(actor, "line_manager"):
            return Response({"detail": "Only the line manager can recommend a contract action."}, status=403)
        action_value = request.data.get("action")
        if action_value not in ContractRenewalDecision.Action.values:
            return Response({"detail": "Invalid action."}, status=400)
        try:
            decision = recommend_contract_action(
                version, actor=actor, action=action_value,
                comment=request.data.get("comment", ""), end_date=request.data.get("end_date") or None,
            )
        except ContractDecisionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(ContractRenewalDecisionSerializer(decision).data)

    @action(detail=True, methods=["post"])
    def decide_contract(self, request, pk=None):
        version = self.get_object()
        actor = get_request_employee(request)
        if actor is None or not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can decide a contract action."}, status=403)
        action_value = request.data.get("action")
        if action_value not in ContractRenewalDecision.Action.values:
            return Response({"detail": "Invalid action."}, status=400)
        try:
            decision = decide_contract_action(
                version, actor=actor, action=action_value,
                comment=request.data.get("comment", ""), end_date=request.data.get("end_date") or None,
            )
        except ContractDecisionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(ContractRenewalDecisionSerializer(decision).data)
```

Add the new imports to `views.py`: `from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action`, `ContractRenewalDecision` to the `.models` import line, `ContractRenewalDecisionSerializer` to the `.serializers` import line.

Note on `RowScopePermission` and these actions: both are `detail=True`, so DRF's `get_object()` already runs `RowScopePermission.has_object_permission()` (via `EmployeeVersionViewSet`'s existing `get_target_employee`) before either action body executes — an hr_admin/auditor (row_scope=ALL) or the target's own manager reaches the body; anyone else already gets a `RowScopePermission`-driven 403 before the `has_role` check even runs. The `has_role` checks above are the *action*-specific narrowing on top of that (row access alone doesn't mean "is this specific person's manager" is who's asking — an auditor has row access too, but must never be allowed to recommend).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test core_hr.test_api.ContractActionApiTests -v 2`
Expected: PASS.

- [ ] **Step 6: Run the full core_hr suite + system checks**

Run: `cd hcm/backend && python manage.py test core_hr -v 2 && python manage.py check`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hcm/backend/core_hr/serializers.py hcm/backend/core_hr/views.py hcm/backend/core_hr/test_api.py
git commit -m "core_hr: recommend_contract/decide_contract API actions"
```

---

### Task 4: Reminders — settings, `core_hr/tasks.py`, `CELERY_BEAT_SCHEDULE`

**Files:**
- Modify: `hcm/backend/config/settings.py` (new settings, `CELERY_BEAT_SCHEDULE`)
- Create: `hcm/backend/core_hr/contract_reminders.py`
- Create: `hcm/backend/core_hr/tasks.py`
- Test: `hcm/backend/core_hr/test_reminders.py`

**Interfaces:**
- Consumes: `notifications.services.notify(*, recipient: Employee, kind: str, title: str, body: str = "", link: str = "", email: bool = True) -> Notification`, `notifications.services.notify_many(recipients, *, kind, title, body="", link="", email=True) -> list[Notification]`, `notifications.services.employees_with_role(role_name: str)` (confirmed against `notifications/services.py:23,32,46` and `performance/reminders.py`'s real call sites).
- Produces: `run_contract_reminders(dry_run=False) -> dict`, Celery task `core_hr.tasks.run_contract_reminders_task`, settings `CONTRACT_REMINDER_OFFSETS_DAYS`, `CONTRACT_ESCALATION_DAYS`.

- [ ] **Step 1: Write the failing test**

Create `hcm/backend/core_hr/test_reminders.py`:

```python
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rbac_audit.models import Role, RoleAssignment

from .contract_reminders import run_contract_reminders
from .models import ContractRenewalDecision, Department, Employee, EmployeeVersion, Location, OccupationalLevel


class ContractRemindersTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=3)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager4@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.hr_admin = Employee.objects.hire(
            employee_number="E801", first_name="HR", last_name="Admin",
            date_of_birth=date(1980, 1, 1), work_email="hradmin4@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        # Role/RoleAssignment field names below are the shape used throughout
        # this codebase's other test fixtures (e.g. establishment/tests.py) —
        # confirm against one of those before trusting verbatim.
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

    def _hire_fixed_term(self, *, number, end_date, manager=None):
        return Employee.objects.hire(
            employee_number=number, first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email=f"{number.lower()}@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=end_date, manager=manager or self.manager,
        )

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify")
    def test_manager_reminded_on_offset_day(self, mock_notify):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs["recipient"], self.manager)

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify")
    def test_no_reminder_off_offset(self, mock_notify):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=29))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        mock_notify.assert_not_called()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_hr_admin_escalation_when_no_recommendation(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify_many.assert_called_once()
        self.assertEqual(list(mock_notify_many.call_args.args[0]), [self.hr_admin])

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_manager_not_reminded_once_recommendation_exists(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        employee = self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        ContractRenewalDecision.objects.create(
            employee_version=employee.current_version, status=ContractRenewalDecision.Status.RECOMMENDED,
        )
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify.assert_not_called()
        mock_notify_many.assert_called_once()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_no_reminders_once_decided(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        employee = self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        ContractRenewalDecision.objects.create(
            employee_version=employee.current_version, status=ContractRenewalDecision.Status.DECIDED,
            decided_action=ContractRenewalDecision.Action.CONVERT_PERMANENT,
        )
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        self.assertEqual(result["hr_admin_reminders"], 0)
        mock_notify.assert_not_called()
        mock_notify_many.assert_not_called()

    def test_beat_schedule_registered(self):
        from django.conf import settings

        self.assertIn("run-contract-reminders-daily", settings.CELERY_BEAT_SCHEDULE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hcm/backend && python manage.py test core_hr.test_reminders -v 2`
Expected: FAIL — `core_hr.contract_reminders` doesn't exist.

- [ ] **Step 3: Settings**

In `hcm/backend/config/settings.py`, near the end of the file (matching where `POSITION_APPROVAL_CHAIN` was added in C1 part 1):

```python
CONTRACT_REMINDER_OFFSETS_DAYS = [
    int(d) for d in os.environ.get("CONTRACT_REMINDER_OFFSETS_DAYS", "60,30,14,7").split(",")
]
CONTRACT_ESCALATION_DAYS = int(os.environ.get("CONTRACT_ESCALATION_DAYS", "14"))
```

Add to `CELERY_BEAT_SCHEDULE` (the dict at line 257-269), following the existing two entries' shape exactly:

```python
    "run-contract-reminders-daily": {
        "task": "core_hr.tasks.run_contract_reminders_task",
        "schedule": 24 * 60 * 60,  # daily; crontab(hour=7) once beat runs against a real broker
    },
```

- [ ] **Step 4: `core_hr/contract_reminders.py`**

`notify`/`notify_many`/`employees_with_role` are real, already-confirmed functions (see this task's Interfaces block above — `notifications/services.py:23,32,46`), not guesses:

```python
"""Daily reminder sweep for fixed-term contracts approaching expiry (C1
part 2). Mirrors performance/reminders.py's shape, minus that module's
ReminderLog-based dedup: this task's query is a narrow exact-offset-day
match (not a range) and fires via Celery beat once daily, so the only
double-send risk is a manual re-run on the same day -- accepted as a
minor, non-critical-path simplification (an extra in-app nudge, not a
duplicate decision or data change) rather than building PC-1-scale
tracking infrastructure for a single-recipient-per-event feature. See
design spec §5."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from notifications.services import employees_with_role, notify, notify_many

from .models import ContractRenewalDecision, EmployeeVersion


def run_contract_reminders(*, dry_run: bool = False) -> dict:
    today = timezone.localdate()
    offsets = set(settings.CONTRACT_REMINDER_OFFSETS_DAYS)
    escalation_days = settings.CONTRACT_ESCALATION_DAYS

    manager_reminders = 0
    hr_admin_versions = []  # [(version, employee_name, reason), ...]

    versions = EmployeeVersion.objects.current().filter(
        employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
        contract_end_date__isnull=False,
    ).select_related("employee", "manager")

    for version in versions:
        days_remaining = (version.contract_end_date - today).days
        if days_remaining not in offsets:
            continue

        decision = getattr(version, "contract_renewal_decision", None)
        if decision is not None and decision.status == ContractRenewalDecision.Status.DECIDED:
            continue

        employee_name = f"{version.employee.first_name} {version.employee.last_name}"

        if decision is None:
            if version.manager is not None:
                if not dry_run:
                    notify(
                        recipient=version.manager, kind="contract_reminder",
                        title=f"{employee_name}'s fixed-term contract ends {version.contract_end_date:%d %b %Y}",
                        body="Recommend renew, convert to permanent, or let lapse.",
                        link="/contract-renewals",
                    )
                manager_reminders += 1
            if days_remaining <= escalation_days:
                hr_admin_versions.append((version, employee_name, "no recommendation yet"))
        else:  # RECOMMENDED
            hr_admin_versions.append((version, employee_name, "awaiting your decision"))

    hr_admin_reminders = 0
    if hr_admin_versions:
        hr_admins = list(employees_with_role("hr_admin"))
        for version, employee_name, reason in hr_admin_versions:
            if hr_admins and not dry_run:
                notify_many(
                    hr_admins, kind="contract_reminder",
                    title=f"{employee_name}'s fixed-term contract ends {version.contract_end_date:%d %b %Y} ({reason})",
                    body="Review at /contract-renewals.",
                    link="/contract-renewals",
                )
            hr_admin_reminders += 1

    return {"manager_reminders": manager_reminders, "hr_admin_reminders": hr_admin_reminders}
```

Note the count/notify split for hr_admin: `hr_admin_reminders` counts *events* (one per expiring contract needing hr_admin's attention), while each event notifies *every* hr_admin via one `notify_many` call — matching `notifications/services.py`'s own stated rationale for that function ("policy-publish-to-everyone and similar broadcasts create every row in one query instead of N"). Tests below assert on event counts and on `notify_many` being called with the current hr_admin list, not on a per-recipient count.

- [ ] **Step 5: `core_hr/tasks.py`**

```python
"""Celery tasks for core_hr (C1 part 2). Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py)."""
from celery import shared_task

from .contract_reminders import run_contract_reminders


@shared_task(name="core_hr.tasks.run_contract_reminders_task")
def run_contract_reminders_task(dry_run: bool = False) -> dict:
    return run_contract_reminders(dry_run=dry_run)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd hcm/backend && python manage.py test core_hr.test_reminders -v 2`
Expected: PASS.

- [ ] **Step 7: Run the full core_hr suite + system checks**

Run: `cd hcm/backend && python manage.py test core_hr -v 2 && python manage.py check`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add hcm/backend/config/settings.py hcm/backend/core_hr/contract_reminders.py hcm/backend/core_hr/tasks.py hcm/backend/core_hr/test_reminders.py
git commit -m "core_hr: daily contract-expiry reminder + escalation task"
```

---

### Task 5: Frontend — `/contract-renewals` page, types, nav/route

**Files:**
- Modify: `hcm/frontend/src/api/types.ts`
- Create: `hcm/frontend/src/pages/ContractRenewalsPage.tsx`
- Modify: `hcm/frontend/src/layout/navConfig.ts`
- Modify: `hcm/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/employee-versions/?fixed_term=true&current=true`, `POST /api/v1/employee-versions/{id}/recommend_contract/`, `POST /api/v1/employee-versions/{id}/decide_contract/` (Task 3).

- [ ] **Step 1: Types**

In `hcm/frontend/src/api/types.ts`, read the current `EmployeeVersion` interface first (it must already exist, given `EmployeeVersionSerializer` has backed a frontend view since Sprint 3) and add the two new fields to it: `contract_end_date: string | null` and `contract_renewal_decision: ContractRenewalDecision | null`. Add the new type:

```typescript
export type ContractAction = 'renew' | 'convert_permanent' | 'let_lapse'
export type ContractDecisionStatus = 'recommended' | 'decided'

export interface ContractRenewalDecision {
  id: number
  status: ContractDecisionStatus
  recommended_action: ContractAction | null
  recommended_by: number | null
  recommended_at: string | null
  recommended_comment: string
  recommended_end_date: string | null
  decided_action: ContractAction | null
  decided_by: number | null
  decided_at: string | null
  decided_comment: string
  decided_end_date: string | null
  resulting_employee_version: number | null
}

export const CONTRACT_ACTION_LABELS: Record<ContractAction, string> = {
  renew: 'Renew',
  convert_permanent: 'Convert to permanent',
  let_lapse: 'Let lapse',
}
```

- [ ] **Step 2: `ContractRenewalsPage.tsx`**

Model this closely on `hcm/frontend/src/pages/PositionsPage.tsx` (read it first — same three-tier shape: page owns the list query + summary + per-row actions, a row component owns its own busy/error state, `useAllPages` for the list fetch, `api.post` + `ApiError` for actions, `hasRole` for gating). Cover, per design spec §9:
- List fetched via `useAllPages<EmployeeVersion>('/employee-versions/?fixed_term=true&current=true', [], 'Failed to load contracts.')`.
- Each row shows the employee, manager, `contract_end_date`, and `contract_renewal_decision?.status ?? 'none'`.
- A "Recommend" action visible only when `hasRole('line_manager')` and the row's `manager` is the current user and `contract_renewal_decision` is null — a form to pick an action (+ end date if RENEW, + comment), posting to `recommend_contract`.
- A "Decide" action visible only when `hasRole('hr_admin')` and `contract_renewal_decision?.status !== 'decided'` — pre-filled from `contract_renewal_decision?.recommended_action`/`recommended_end_date` if present, editable, posting to `decide_contract`.
- Summary stats block: count where `days until contract_end_date <= 60` (mirror whatever the backend's `CONTRACT_REMINDER_OFFSETS_DAYS[0]` default is, computed client-side from `contract_end_date`), count where `contract_renewal_decision` is null and days remaining `<= 14` (escalation threshold, same client-side computation), count where `contract_renewal_decision?.status === 'decided'` and `decided_at` falls within the current calendar month.

- [ ] **Step 3: Nav + route**

In `hcm/frontend/src/layout/navConfig.ts`, add a new role group and nav entry (place near `/positions`, given both are establishment/HR-administration concerns):

```typescript
const CONTRACTS = ['hr_admin', 'line_manager', 'auditor'] as const
```
```typescript
  { to: '/contract-renewals', label: 'Contract Renewals', roles: CONTRACTS },
```

In `hcm/frontend/src/App.tsx`, add the route wrapped in `RequireRole` with the same `CONTRACTS` role set, following the exact pattern every other role-scoped route already uses (read a neighboring `<Route element={<RequireRole roles={[...]} />}>` block and match its structure precisely — do not leave this route unguarded, unlike the mistake caught and fixed on `/positions` in C1 part 1).

- [ ] **Step 4: Typecheck, lint, build**

Run: `cd hcm/frontend && npx tsc -b && npm run lint && npm run build`
Expected: clean.

- [ ] **Step 5: Manual browser smoke check**

Start both dev servers (`python manage.py runserver` / `npm run dev`). Log in as `hradmin`, use Django admin (or a quick `manage.py shell` command) to set an existing fixed-term employee's `contract_end_date` to a near-future date if none of the seeded data already has one. Log in as `manager` and confirm the contract appears in `/contract-renewals` with a "Recommend" action; recommend a renewal. Log in as `hradmin` and confirm the recommendation appears pre-filled on the "Decide" action; decide to renew. Confirm the row now shows `decided`, and (via `/employees` or Django admin) confirm the employee has a new current `EmployeeVersion` with the extended `contract_end_date`.

- [ ] **Step 6: Commit**

```bash
git add hcm/frontend/src/api/types.ts hcm/frontend/src/pages/ContractRenewalsPage.tsx hcm/frontend/src/layout/navConfig.ts hcm/frontend/src/App.tsx
git commit -m "frontend: contract renewals page (recommend/decide workflow)"
```

---

### Task 6: End-to-end browser test

**Files:**
- Create: `hcm/frontend/e2e/contract-renewals.spec.ts`
- Modify (if needed): `hcm/backend/core_hr/management/commands/seed_demo_data.py` (only if no seeded fixed-term employee with a suitable `contract_end_date` exists for the test to use — check first)

**Interfaces:**
- Consumes: `e2e/helpers.ts` (`login`, `expectHeading`, `settled`, `logout` — use the canonical `logout` helper this time, not an inline sign-out sequence, per the Minor finding noted against C1 part 1's own e2e test).

- [ ] **Step 1: Confirm or add e2e-usable fixture data**

Check `seed_demo_data.py` for an existing fixed-term employee with a `manager` set and a `contract_end_date` within a range this test can exercise (e.g. expiring in the next 90 days relative to whatever "today" the seed uses). If none exists, add one following the exact pattern the other fixture employees in that file already use — a fixed-term hire with `contract_end_date` set and `manager=` pointing at the existing `manager`/`eng_head` fixture.

- [ ] **Step 2: Write the e2e test**

```typescript
// hcm/frontend/e2e/contract-renewals.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

test.describe('Contract end-date tracking & renewal decisions (C1 part 2)', () => {
  test('manager recommends -> hr_admin decides -> new version reflects the outcome', async ({ page }) => {
    await login(page, 'manager')
    await page.goto('/contract-renewals')
    await expectHeading(page, 'Contract Renewals')
    await settled(page)

    const row = page.locator('tr', { hasText: 'Contractor' })  // match the seeded fixed-term employee's surname
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Recommend' }).click()
    await page.getByLabel('Action').selectOption('renew')
    await page.getByLabel('New end date').fill('2027-12-31')
    await page.getByRole('button', { name: 'Submit recommendation' }).click()
    await settled(page)
    await expect(row).toContainText('Recommended')

    await logout(page)
    await login(page, 'hradmin')
    await page.goto('/contract-renewals')
    await settled(page)
    const hrRow = page.locator('tr', { hasText: 'Contractor' })
    await hrRow.getByRole('button', { name: 'Decide' }).click()
    await expect(page.getByLabel('Action')).toHaveValue('renew')  // pre-filled from the recommendation
    await page.getByRole('button', { name: 'Submit decision' }).click()
    await settled(page)
    await expect(hrRow).toContainText('Decided')
  })
})
```

**This is illustrative of the flow to cover, not guaranteed-exact selectors** — Task 5's page was built after this plan was written; read the real `ContractRenewalsPage.tsx` and adjust selectors/button labels/form field labels to match reality before trusting this code, the same discipline C1 part 1's own e2e task applied.

- [ ] **Step 3: Run the test, iterate on selectors, then the full suite**

Run: `cd hcm/frontend && npx playwright test contract-renewals.spec.ts`
Expected: pass once selectors are verified against the real page.

Run: `cd hcm/frontend && npm test`
Expected: full suite green, modulo the already-known pre-existing `core-hr.spec.ts` timing flake (confirmed unrelated, C1 part 1) — no *new* failures.

- [ ] **Step 4: Commit**

```bash
git add hcm/frontend/e2e/contract-renewals.spec.ts
git commit -m "e2e: contract renewal recommend/decide browser test"
```
(add `hcm/backend/core_hr/management/commands/seed_demo_data.py` too if Step 1 required a change)

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** §1-2 (purpose/scope) — no code, framing only. §3 (data model) — Task 1. §4 (decision flow) — Task 2. §5 (reminders/escalation) — Task 4. §6 (access control) — Task 3, via `RowScopePermission` + inline role checks rather than the spec's originally-described bespoke `ContractPermission` class (see the plan header's note — behavior-identical, mechanism refined during plan research). §7 (data-quality registry) — Task 1. §8 (why core_hr) — architectural decision, no dedicated task, reflected in every task's file placement. §9 (frontend) — Task 5. §10 (testing) — spread across every task's own test steps + Task 6. §11 (known boundaries) — documentation, no task needed.
- **Task 4's `notify()`/`notify_many()`/`employees_with_role()` calls were initially left as placeholders during drafting, then resolved for real during self-review** (`notifications/services.py:23,32,46`, cross-checked against `performance/reminders.py`'s real call sites) rather than shipped as an implementer research instruction — the first draft's "go find this yourself" framing was a shortcut this plan shouldn't have taken given the tools to just check were available. Fixed inline, including a real bug the placeholder version had masked: `manager_reminders` was incrementing even when `version.manager` was `None` (no notification actually sent) — the real code only counts when a manager exists to receive one.
- **Type/signature consistency checked:** `recommend_contract_action`/`decide_contract_action`'s signatures match between Task 2 (definition) and Task 3 (call sites) exactly. `ContractRenewalDecision.Action`/`Status` choices are used identically across Tasks 1, 2, 3, 4, and the frontend's `ContractAction` type in Task 5. `EmploymentEvent.EventType.CONTRACT_RENEWAL` is defined once (Task 1) and consumed once (Task 2). Task 4's test fixtures were missing an `hr_admin` employee/role fixture entirely in the first draft (would have made every hr_admin-reminder assertion fail against the real `employees_with_role("hr_admin")` — an empty queryset, not a mock) — added.
- **Placeholder scan:** no remaining TBD/TODO/guessed signatures. The one honest, deliberate simplification left in the plan (not a placeholder — a reasoned scope decision, stated as such): Task 4 has no `ReminderLog`-style dedup the way `performance/reminders.py` does, accepting a narrow same-day-rerun double-notify risk rather than building tracking infrastructure sized for a much simpler, single-recipient feature.
- **Row-scope reuse is the plan's one substantive addition beyond the spec's own text** — flagged prominently in the header rather than buried, since a future reader diffing this plan against the spec should understand why `ContractPermission` never appears as a real class.
