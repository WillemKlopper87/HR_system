from rbac_audit.drf import TieredModelSerializer
from rest_framework import serializers

from .models import (
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
    JobGrade,
    Location,
    OccupationalLevel,
)


class EmployeeVersionSerializer(TieredModelSerializer):
    class Meta:
        model = EmployeeVersion
        fields = [
            "id", "employee", "valid_from", "valid_to", "department", "job_title",
            "occupational_level", "job_grade", "manager", "employment_status",
            "citizenship_status", "location", "race", "gender", "disability_status",
            "disability_detail", "race_source", "disability_source",
        ]


class EmployeeSerializer(TieredModelSerializer):
    """Identity fields only (Data-Dictionary.md core_hr.Employee) — current
    department/job title/status come from EmployeeVersion (?current=true),
    kept as a separate fetch rather than duplicated here so tiering logic
    for time-varying attributes stays in one place (EmployeeVersionSerializer)."""

    class Meta:
        model = Employee
        fields = [
            "id", "employee_number", "first_name", "last_name", "preferred_name",
            "national_id_number", "passport_number", "date_of_birth", "work_email",
            "personal_email", "phone", "hire_date",
        ]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code", "parent", "active"]


class OccupationalLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = OccupationalLevel
        fields = ["id", "name", "code", "order", "active"]


class JobGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobGrade
        fields = ["id", "name", "code", "occupational_level", "active"]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "province", "active"]


class DataQualityExceptionSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = DataQualityException
        fields = [
            "id", "employee", "employee_number", "employee_name",
            "exception_type", "detail", "detected_at", "resolved_at",
        ]
        read_only_fields = ["employee", "exception_type", "detail", "detected_at"]

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"
