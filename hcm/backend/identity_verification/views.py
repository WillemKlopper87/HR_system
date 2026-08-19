from __future__ import annotations

from core_hr.models import Employee
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.consent import record_consent
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import has_role
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import BiometricEnrollment, LivenessCheck
from .permissions import IsSelfOrHRAdmin
from .serializers import (
    BiometricEnrollmentCreateSerializer,
    BiometricEnrollmentSerializer,
    LivenessCheckCreateSerializer,
    LivenessCheckSerializer,
    ReviewDecisionSerializer,
)
from .services import (
    ConsentRequiredError,
    EnrollmentRequiredError,
    ReviewError,
    enroll_employee,
    resolve_review,
    run_liveness_check,
    weekly_office_attendance,
)


def _visible_queryset(request, base):
    employee = get_request_employee(request)
    if employee is None:
        return base.none()
    if has_role(employee, "hr_admin") or has_role(employee, "auditor"):
        return base
    return base.filter(employee_id=employee.id)


class BiometricEnrollmentViewSet(viewsets.ModelViewSet):
    """No PATCH/DELETE — re-enrollment overwrites the existing row via
    create() (services.py::enroll_employee uses update_or_create), so
    there's never a need to edit one directly."""

    serializer_class = BiometricEnrollmentSerializer
    permission_classes = [IsSelfOrHRAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        base = BiometricEnrollment.objects.select_related("employee", "enrolled_by")
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            base = base.filter(employee_id=target_id)
        return _visible_queryset(self.request, base)

    def create(self, request, *args, **kwargs):
        input_serializer = BiometricEnrollmentCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        employee = input_serializer.validated_data["employee"]
        actor = get_request_employee(request)
        if actor is None or (actor.id != employee.id and not has_role(actor, "hr_admin")):
            raise PermissionDenied("Only the employee themself or hr_admin can enroll this employee.")
        try:
            enrollment = enroll_employee(
                employee=employee, descriptor=input_serializer.validated_data["descriptor"], actor=actor
            )
        except ConsentRequiredError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(BiometricEnrollmentSerializer(enrollment).data, status=201)


class LivenessCheckViewSet(viewsets.ModelViewSet):
    """No PATCH/DELETE on a check itself — the only mutation after
    creation is the dedicated review action, which enforces its own
    state-machine rule (services.py::resolve_review — only a PENDING
    check can be reviewed, exactly once)."""

    serializer_class = LivenessCheckSerializer
    permission_classes = [IsSelfOrHRAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        base = LivenessCheck.objects.select_related("employee", "requested_by", "reviewed_by")
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            base = base.filter(employee_id=target_id)
        return _visible_queryset(self.request, base)

    def create(self, request, *args, **kwargs):
        input_serializer = LivenessCheckCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data
        employee = data["employee"]
        actor = get_request_employee(request)
        if actor is None or (actor.id != employee.id and not has_role(actor, "hr_admin")):
            raise PermissionDenied("Only the employee themself or hr_admin can run this check.")
        trigger = LivenessCheck.Trigger.SELF if actor.id == employee.id else LivenessCheck.Trigger.HR_REQUESTED
        try:
            check = run_liveness_check(
                employee=employee, descriptor=data.get("descriptor"), latitude=data.get("latitude"),
                longitude=data.get("longitude"), trigger=trigger,
                requested_by=actor if actor.id != employee.id else None,
            )
        except (ConsentRequiredError, EnrollmentRequiredError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(LivenessCheckSerializer(check).data, status=201)

    @action(detail=False, methods=["post"])
    def consent(self, request):
        employee_id = request.data.get("employee")
        if not employee_id:
            return Response({"detail": "employee is required."}, status=400)
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"detail": "No such employee."}, status=400)
        actor = get_request_employee(request)
        if actor is None or (actor.id != employee.id and not has_role(actor, "hr_admin")):
            return Response({"detail": "Only the employee themself or hr_admin can capture this consent."}, status=403)
        record_consent(
            employee=employee, purpose=ConsentRecord.Purpose.BIOMETRIC,
            lawful_basis=request.data.get("lawful_basis", ConsentRecord.LawfulBasis.CONSENT),
            text_version=request.data.get("text_version", "v1"), actor=actor,
        )
        return Response({"detail": "Consent recorded."}, status=201)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        check = self.get_object()
        actor = get_request_employee(request)
        if not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can review a flagged check."}, status=403)
        input_serializer = ReviewDecisionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            resolve_review(
                check, reviewer=actor, decision=input_serializer.validated_data["decision"],
                notes=input_serializer.validated_data.get("notes", ""),
            )
        except ReviewError as exc:
            return Response({"detail": str(exc)}, status=400)
        check.refresh_from_db()
        return Response(self.get_serializer(check).data)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def attendance_summary(request):
    """hr_admin/auditor: org-wide weekly office-attendance compliance
    (policy: 2 days/week, geo.py::REQUIRED_OFFICE_DAYS_PER_WEEK) —
    includes employees with zero check-ins ever, since that's the
    strongest single signal worth surfacing to HR. A plain employee gets
    just their own row."""
    actor = get_request_employee(request)
    if actor is None:
        return Response({"detail": "Not authenticated."}, status=401)

    employees = Employee.objects.all() if (has_role(actor, "hr_admin") or has_role(actor, "auditor")) else Employee.objects.filter(pk=actor.id)

    rows = []
    for employee in employees:
        summary = weekly_office_attendance(employee)
        rows.append({
            "employee": employee.id,
            "employee_number": employee.employee_number,
            "employee_name": f"{employee.first_name} {employee.last_name}",
            **summary,
        })
    return Response(rows)
