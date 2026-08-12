from rbac_audit.drf import TieredModelSerializer

from .models import EmployeeVersion


class EmployeeVersionSerializer(TieredModelSerializer):
    class Meta:
        model = EmployeeVersion
        fields = [
            "id", "employee", "valid_from", "valid_to", "department", "job_title",
            "occupational_level", "job_grade", "manager", "employment_status",
            "citizenship_status", "location", "race", "gender", "disability_status",
            "disability_detail", "race_source", "disability_source",
        ]
