"""Org-structure reference tables. Split out of models.py (HR_Code_report.md
M5) -- no behavior change; see core_hr/models/__init__.py for the app's
overall split. Defined first (imported first by __init__.py) since
EmployeeVersion in core.py holds direct FKs to these classes."""
from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from ..base import TimestampedModel


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
