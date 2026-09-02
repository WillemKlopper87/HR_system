"""Org-structure reference tables (Department/OccupationalLevel/JobGrade/
Location). Split out of views.py (HR_Code_report.md M5) -- no behavior
change; see that module's own docstring for the app's overall split."""
from __future__ import annotations

from django.db.models.deletion import ProtectedError
from rest_framework import permissions, viewsets

from .models import Department, JobGrade, Location, OccupationalLevel
from .permissions import IsHRAdminOrReadOnly
from .serializers import DepartmentSerializer, JobGradeSerializer, LocationSerializer, OccupationalLevelSerializer


class ProtectedDeleteMixin:
    """Reference tables (Department/JobGrade/Location) are PROTECTed
    against deletion while in use (employee_versions FK). Surface that as
    a 400 with a clear message instead of DRF's default 500."""

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "This record is still referenced by employee records and cannot be deleted. "
                "Mark it inactive instead."
            )


class DepartmentViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class OccupationalLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """The six statutory EEA occupational levels are fixed by law and
    seeded via migration — not user-manageable, hence read-only."""

    queryset = OccupationalLevel.objects.all()
    serializer_class = OccupationalLevelSerializer
    permission_classes = [permissions.IsAuthenticated]


class JobGradeViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = JobGrade.objects.select_related("occupational_level").all()
    serializer_class = JobGradeSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class LocationViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsHRAdminOrReadOnly]
