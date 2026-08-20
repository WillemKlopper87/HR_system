from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .base import TimestampedModel


class Department(TimestampedModel):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.PROTECT
    )
    active = models.BooleanField(default=True)
    # The matching department in the collab platform (ADR-011), resolved by
    # `manage.py sync_collab_ids` (name match) or set by hand; blank = not
    # mapped, so reminders for this department stay HCM-only.
    collab_department_id = models.CharField(max_length=64, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OccupationalLevel(TimestampedModel):
    """The six statutory EEA occupational levels (EEA9). Seeded by a data
    migration — see HR_system/EEA-Form-Spec-Notes.md."""

    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    order = models.PositiveSmallIntegerField(unique=True)
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class JobGrade(TimestampedModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    occupational_level = models.ForeignKey(
        OccupationalLevel, on_delete=models.PROTECT, related_name="job_grades"
    )
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["occupational_level__order", "name"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Location(TimestampedModel):
    class Province(models.TextChoices):
        EASTERN_CAPE = "EC", "Eastern Cape"
        FREE_STATE = "FS", "Free State"
        GAUTENG = "GP", "Gauteng"
        KWAZULU_NATAL = "KZN", "KwaZulu-Natal"
        LIMPOPO = "LP", "Limpopo"
        MPUMALANGA = "MP", "Mpumalanga"
        NORTHERN_CAPE = "NC", "Northern Cape"
        NORTH_WEST = "NW", "North West"
        WESTERN_CAPE = "WC", "Western Cape"
        OUTSIDE_SA = "OUT", "Outside South Africa"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    province = models.CharField(max_length=3, choices=Province.choices, blank=True)
    active = models.BooleanField(default=True)
    # Office geofence centre — optional (Sprint 12b: identity_verification's
    # office-attendance check needs this to know what "at the office" means
    # for a given Location; blank until an admin sets it for a site).
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EmployeeManager(models.Manager):
    @transaction.atomic
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
        contract_end_date=None,
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
        """Create an employee and their opening EmployeeVersion + HIRE event
        in one step. This is the single entry point bulk import (and later,
        recruitment's hire-to-employee flow) calls, per the sprint plan's
        'no re-entry' rule."""
        employee = self.create(
            employee_number=employee_number,
            first_name=first_name,
            last_name=last_name,
            preferred_name=preferred_name,
            national_id_number=national_id_number,
            passport_number=passport_number,
            date_of_birth=date_of_birth,
            work_email=work_email,
            personal_email=personal_email,
            phone=phone,
            hire_date=hire_date,
            user=user,
        )
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
            contract_end_date=contract_end_date,
            race=race or EmployeeVersion.Race.NOT_DISCLOSED,
            gender=gender or EmployeeVersion.Gender.NOT_DISCLOSED,
            disability_status=disability_status or EmployeeVersion.DisabilityStatus.NOT_DISCLOSED,
            disability_detail=disability_detail,
            race_source=race_source or EmployeeVersion.DemographicSource.IMPORTED,
            disability_source=disability_source or EmployeeVersion.DemographicSource.IMPORTED,
        )
        EmploymentEvent.objects.create(
            employee=employee,
            event_type=EmploymentEvent.EventType.HIRE,
            effective_date=hire_date,
            from_version=None,
            to_version=version,
        )
        return employee


VERSION_CARRY_FIELDS = (
    "department", "job_title", "occupational_level", "job_grade", "manager",
    "employment_status", "citizenship_status", "location", "position",
    "contract_end_date",
    "race", "gender", "disability_status", "disability_detail",
    "race_source", "disability_source",
)


class Employee(TimestampedModel):
    employee_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=150, blank=True)
    # Restricted-tier field (Data-Dictionary.md): protected at rest by
    # Postgres disk encryption (ADR-005); column-level encryption is a
    # follow-up ADR, not yet implemented.
    national_id_number = models.CharField(max_length=13, blank=True)
    passport_number = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField()
    work_email = models.EmailField(unique=True)
    # The same person's user id in the collab platform (ADR-011), resolved by
    # work email via `manage.py sync_collab_ids`; blank = no collab account, so
    # this employee gets no pushed reminders (HCM-only).
    collab_user_id = models.CharField(max_length=64, blank=True)
    personal_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    hire_date = models.DateField()
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
    )

    objects = EmployeeManager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["employee_number"]

    def __str__(self):
        return f"{self.employee_number} — {self.first_name} {self.last_name}"

    def version_as_at(self, as_of_date):
        return self.versions.as_at(as_of_date).first()

    @property
    def current_version(self):
        return self.version_as_at(timezone.localdate())

    @transaction.atomic
    def apply_lifecycle_event(
        self, *, event_type, effective_date, termination_reason="", notes="", **field_updates
    ):
        """Close the currently open EmployeeVersion and, for every event
        type except TERMINATION, open a new one carrying the prior
        attributes forward with `field_updates` applied. Records the
        EmploymentEvent linking both versions — this is the EEA2
        workforce-movement data (promotions/transfers/terminations)."""
        current = self.versions.select_for_update().filter(valid_to__isnull=True).first()
        if current is None:
            raise ValueError(f"Employee {self.employee_number} has no open version to close")
        if effective_date <= current.valid_from:
            raise ValueError("effective_date must be after the current version's valid_from")

        current.valid_to = effective_date
        current.save(update_fields=["valid_to"])

        new_version = None
        if event_type != EmploymentEvent.EventType.TERMINATION:
            carried = {f: getattr(current, f) for f in VERSION_CARRY_FIELDS}
            carried.update(field_updates)
            new_version = EmployeeVersion.objects.create(
                employee=self, valid_from=effective_date, valid_to=None, **carried
            )

        return EmploymentEvent.objects.create(
            employee=self,
            event_type=event_type,
            effective_date=effective_date,
            termination_reason=termination_reason,
            from_version=current,
            to_version=new_version,
            notes=notes,
        )


class EmployeeVersionQuerySet(models.QuerySet):
    def as_at(self, as_of_date):
        return self.filter(valid_from__lte=as_of_date).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=as_of_date)
        )

    def current(self):
        return self.as_at(timezone.localdate())


class EmployeeVersion(TimestampedModel):
    class EmploymentStatus(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        FIXED_TERM = "fixed_term", "Fixed-term"
        TEMPORARY = "temporary", "Temporary (< 3 months)"
        LEARNER = "learner", "Learner"

    class CitizenshipStatus(models.TextChoices):
        SA_CITIZEN_BIRTH_DESCENT = "sa_citizen_birth_descent", "SA citizen (birth or descent)"
        SA_NATURALISED_PRE_1994 = "sa_naturalised_pre_1994", "SA naturalised before 27 Apr 1994"
        SA_NATURALISED_POST_1994 = "sa_naturalised_post_1994", "SA naturalised after 26 Apr 1994"
        FOREIGN_NATIONAL = "foreign_national", "Foreign national"

    class Race(models.TextChoices):
        AFRICAN = "african", "African"
        COLOURED = "coloured", "Coloured"
        INDIAN = "indian", "Indian"
        WHITE = "white", "White"
        NOT_DISCLOSED = "not_disclosed", "Not disclosed"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        NOT_DISCLOSED = "not_disclosed", "Not disclosed"

    class DisabilityStatus(models.TextChoices):
        NO = "no", "No disability"
        YES = "yes", "Disability"
        NOT_DISCLOSED = "not_disclosed", "Not disclosed"

    class DemographicSource(models.TextChoices):
        SELF_IDENTIFIED = "self_identified", "Self-identified (ESS)"
        HR_CAPTURED = "hr_captured", "HR-captured"
        IMPORTED = "imported", "Imported"

    employee = models.ForeignKey(Employee, related_name="versions", on_delete=models.CASCADE)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="employee_versions"
    )
    job_title = models.CharField(max_length=200, blank=True)
    occupational_level = models.ForeignKey(
        OccupationalLevel, on_delete=models.PROTECT, related_name="employee_versions"
    )
    job_grade = models.ForeignKey(
        JobGrade, null=True, blank=True, on_delete=models.PROTECT, related_name="employee_versions"
    )
    manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports"
    )
    employment_status = models.CharField(max_length=20, choices=EmploymentStatus.choices)
    citizenship_status = models.CharField(max_length=30, choices=CitizenshipStatus.choices)
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

    # Meaningful only when employment_status == FIXED_TERM. Nullable by
    # design (no forced backfill for existing fixed-term employees — see
    # data_quality.py's MISSING_CONTRACT_END_DATE check instead). IS in
    # VERSION_CARRY_FIELDS: an unrelated version change (e.g. a promotion)
    # must not silently wipe a still-active contract's end date.
    contract_end_date = models.DateField(null=True, blank=True)

    race = models.CharField(max_length=20, choices=Race.choices, default=Race.NOT_DISCLOSED)
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.NOT_DISCLOSED)
    disability_status = models.CharField(
        max_length=20, choices=DisabilityStatus.choices, default=DisabilityStatus.NOT_DISCLOSED
    )
    disability_detail = models.TextField(blank=True)
    race_source = models.CharField(
        max_length=20, choices=DemographicSource.choices, default=DemographicSource.IMPORTED
    )
    disability_source = models.CharField(
        max_length=20, choices=DemographicSource.choices, default=DemographicSource.IMPORTED
    )

    objects = EmployeeVersionQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["employee", "-valid_from"]
        indexes = [models.Index(fields=["employee", "valid_from", "valid_to"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=models.F("valid_from")),
                name="employeeversion_valid_to_after_valid_from",
            ),
            # Establishment control (C1) derives occupancy rather than
            # storing it: Position.current_occupant/is_vacant/vacant() and
            # recruitment's vacancy check all assume at most one CURRENT
            # version can claim a post. Nothing but this enforced it, and
            # current_occupant's .first() would silently pick one of two
            # concurrent claimants instead of surfacing the conflict.
            # Partial (valid_to IS NULL) on purpose -- a post persists
            # across incumbents, so closed versions of former occupants
            # must never block the next hire into it. NULL position is
            # exempt in both engines' unique semantics, so the many
            # employees holding no post at all are unaffected.
            models.UniqueConstraint(
                fields=["position"],
                condition=models.Q(valid_to__isnull=True),
                name="one_current_occupant_per_position",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_number} as at {self.valid_from}"


class EmploymentEvent(TimestampedModel):
    class EventType(models.TextChoices):
        HIRE = "hire", "Hire"
        PROMOTION = "promotion", "Promotion"
        TRANSFER = "transfer", "Transfer"
        GRADE_CHANGE = "grade_change", "Grade change"
        TERMINATION = "termination", "Termination"
        CONTRACT_CONVERSION = "contract_conversion", "Contract conversion"
        CONTRACT_RENEWAL = "contract_renewal", "Contract renewal"

    class TerminationReason(models.TextChoices):
        RESIGNATION = "resignation", "Resignation"
        DISMISSAL_MISCONDUCT = "dismissal_misconduct", "Dismissal — misconduct"
        DISMISSAL_INCAPACITY = "dismissal_incapacity", "Dismissal — incapacity"
        OPERATIONAL_REQUIREMENTS = "operational_requirements", "Operational requirements"
        RETIREMENT = "retirement", "Retirement"
        DEATH = "death", "Death"
        CONTRACT_END = "contract_end", "Contract end"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, related_name="lifecycle_events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    effective_date = models.DateField()
    termination_reason = models.CharField(max_length=30, choices=TerminationReason.choices, blank=True)
    from_version = models.ForeignKey(
        EmployeeVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_closed"
    )
    to_version = models.ForeignKey(
        EmployeeVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_opened"
    )
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["employee", "effective_date"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.get_event_type_display()} on {self.effective_date}"


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


class DataQualityException(TimestampedModel):
    class ExceptionType(models.TextChoices):
        MISSING_GRADE = "missing_grade", "Missing job grade"
        MISSING_DEMOGRAPHICS = "missing_demographics", "Missing demographics"
        ORPHAN_RECORD = "orphan_record", "Orphan record (no version history)"
        MISSING_CONTRACT_END_DATE = "missing_contract_end_date", "Fixed-term employee missing contract end date"
        # H3: org-wide checks registered from other apps' AppConfig.ready()
        # (data_quality.py's registry — same shape as rbac_audit/retention.py).
        # New types are added here, the shared-kernel model, rather than each
        # app owning its own choices set, the same way every log_access()
        # caller across the app writes AuditLogEntry.Action from one shared list.
        PERFORMANCE_OVERDUE = "performance_overdue", "Overdue performance stage"
        COMP_PROPOSAL_STALE = "comp_proposal_stale", "Compensation proposal awaiting review too long"

    employee = models.ForeignKey(
        Employee, related_name="data_quality_exceptions", on_delete=models.CASCADE
    )
    exception_type = models.CharField(max_length=30, choices=ExceptionType.choices)
    detail = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "exception_type"],
                condition=models.Q(resolved_at__isnull=True),
                name="one_open_exception_per_employee_type",
            )
        ]

    def __str__(self):
        status = "open" if self.resolved_at is None else "resolved"
        return f"{self.employee.employee_number}: {self.get_exception_type_display()} ({status})"
