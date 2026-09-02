"""Dependants and emergency contacts. Split out of models.py
(HR_Code_report.md M5) -- no behavior change; see core_hr/models/__init__.py
for the app's overall split."""
from __future__ import annotations

from django.db import models

from ..base import TimestampedModel
from .core import Employee


class Dependant(TimestampedModel):
    """C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md
    §2.2, §2.9): basic ESS-level dependant records (medical aid/benefits
    context), structurally identical to Employee itself -- no file, no
    consent gate, no workflow -- so it sits next to Employee in the kernel
    rather than in the new `documents` app, which exists specifically for
    file storage + the POPIA review queue. Sensitive-tier by default
    (rbac_audit/tiers.py FIELD_TIERS): this is personal data about a third
    party who holds no seat at this system's RBAC table, a stricter
    default than the employee's own analogous fields."""

    class Relationship(models.TextChoices):
        SPOUSE = "spouse", "Spouse"
        CHILD = "child", "Child"
        PARENT = "parent", "Parent"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="dependants")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=20, choices=Relationship.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    # The dependant's own ID number -- Restricted, same tier as
    # Employee.national_id_number, for the same reason.
    id_number = models.CharField(max_length=13, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["employee", "last_name", "first_name"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.first_name} {self.last_name} ({self.get_relationship_display()})"


class EmergencyContact(TimestampedModel):
    """C2 -- see Dependant's docstring for the placement/tiering reasoning,
    which applies identically here."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=200)
    # Free text, unlike Dependant.relationship -- an emergency contact's
    # relationship label is informational only, nothing downstream branches
    # on it, so it doesn't need a closed choice set.
    relationship = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30)
    alternative_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["employee", "-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_primary=True),
                name="one_primary_emergency_contact_per_employee",
            ),
        ]

    def __str__(self):
        primary = " (primary)" if self.is_primary else ""
        return f"{self.employee.employee_number}: {self.name}{primary}"
