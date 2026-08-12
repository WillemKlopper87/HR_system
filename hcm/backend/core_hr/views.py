from rbac_audit.drf import RowScopePermission, get_request_employee, row_scoped_queryset
from rest_framework import permissions, viewsets

from .models import EmployeeVersion
from .serializers import EmployeeVersionSerializer


class EmployeeVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """Minimal read-only endpoint proving the Sprint 2 RBAC/audit layer
    end-to-end (row-scope + field-tier filtering + audit logging). The
    full employee list/detail UI is Sprint 3's task — this exists so the
    generic layer has a real caller and a real regression baseline."""

    serializer_class = EmployeeVersionSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = EmployeeVersion.objects.select_related(
            "employee", "department", "occupational_level", "job_grade", "manager", "location"
        )
        if self.action != "list":
            # Detail lookups must NOT be row-scope-filtered here: DRF's
            # get_object() raises 404 for anything missing from the
            # queryset before has_object_permission ever runs, which
            # would silently skip RowScopePermission's audit logging.
            # RowScopePermission enforces (and logs) the block instead,
            # yielding 403. List filtering below is still queryset-level
            # for efficiency, since there's no single object to gate.
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee
