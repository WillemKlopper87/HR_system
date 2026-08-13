from __future__ import annotations

import json

from core_hr.models import Employee
from core_hr.permissions import IsHRAdmin
from django.db import models
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rbac_audit.consent import record_consent
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import has_role
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import webhooks
from .models import AssessmentAssignment, ProviderConfig
from .permissions import CanAccessAssessmentAssignment
from .serializers import AssessmentAssignmentSerializer, ProviderConfigSerializer
from .services import ConsentRequiredError, WebhookProcessingError, assign_assessment, process_webhook_result, simulate_provider_completion


class AssessmentAssignmentViewSet(viewsets.ModelViewSet):
    """No PATCH/PUT — an assignment moves through its lifecycle only via
    the consent/simulate_completion actions and the (real) inbound
    webhook, never edited in place (same reasoning as
    compensation.CompProposalViewSet)."""

    serializer_class = AssessmentAssignmentSerializer
    permission_classes = [CanAccessAssessmentAssignment]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        employee = get_request_employee(self.request)
        base = AssessmentAssignment.objects.select_related("employee", "assigned_by").prefetch_related("result")

        target_employee_id = int_query_param(self.request, "employee")
        if target_employee_id is not None:
            base = base.filter(employee_id=target_employee_id)
        applicant_id = int_query_param(self.request, "applicant_id")
        if applicant_id is not None:
            base = base.filter(applicant_id=applicant_id)

        if employee is None:
            return base.none()
        if has_role(employee, "hr_admin") or has_role(employee, "auditor"):
            return base
        q = models.Q(employee_id=employee.id)
        if has_role(employee, "ee_manager"):
            q |= models.Q(employee__isnull=False)
        if has_role(employee, "recruiter"):
            q |= models.Q(applicant_id__isnull=False)
        return base.filter(q)

    def perform_create(self, serializer):
        try:
            serializer.instance = assign_assessment(
                employee=serializer.validated_data.get("employee"),
                applicant_id=serializer.validated_data.get("applicant_id"),
                assessment_type=serializer.validated_data["assessment_type"],
                assigned_by=get_request_employee(self.request),
            )
        except (ConsentRequiredError, ValueError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=False, methods=["post"])
    def consent(self, request):
        """Captures assessment consent for an EMPLOYEE subject (a real
        core_hr.Employee instance is available here, unlike applicant
        subjects — see models.py's AssessmentAssignment docstring).
        Applicant-subject consent goes through the existing
        POST /applicants/{id}/consent/ endpoint with purpose=assessment."""
        employee_id = request.data.get("employee")
        if not employee_id:
            return Response({"detail": "employee is required."}, status=400)
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"detail": "No such employee."}, status=400)

        actor = get_request_employee(request)
        if not (has_role(actor, "hr_admin") or has_role(actor, "ee_manager")):
            return Response({"detail": "Only hr_admin or ee_manager can capture assessment consent."}, status=403)

        record_consent(
            employee=employee,
            purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=request.data.get("lawful_basis", ConsentRecord.LawfulBasis.CONSENT),
            text_version=request.data.get("text_version", "v1"),
            actor=actor,
        )
        return Response({"detail": "Consent recorded."}, status=201)

    @action(detail=True, methods=["post"])
    def simulate_completion(self, request, pk=None):
        """Local-dev/demo trigger standing in for the provider's real
        async webhook delivery — see services.py::simulate_provider_completion."""
        assignment = self.get_object()
        if assignment.status == AssessmentAssignment.Status.COMPLETED:
            return Response({"detail": "This assignment is already completed."}, status=400)
        simulate_provider_completion(assignment)
        assignment.refresh_from_db()
        return Response(self.get_serializer(assignment).data)


class ProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = ProviderConfig.objects.all()
    serializer_class = ProviderConfigSerializer
    permission_classes = [IsHRAdmin]


@csrf_exempt
def assessment_webhook(request):
    """Inbound provider webhook — Architecture-Design.md §6: "versioned
    separately, HMAC-signature-verified with replay protection." Deliberately
    NOT a DRF view: an external provider has no Django session, and DRF's
    SessionAuthentication would still run its CSRF check against an
    anonymous request and reject it outright. Signature verification here
    IS the authentication."""
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    signature = request.headers.get("X-Assessment-Signature", "")
    timestamp = request.headers.get("X-Assessment-Timestamp", "")
    try:
        webhooks.verify_signature(request.body, signature=signature, timestamp=timestamp)
    except webhooks.WebhookVerificationError as exc:
        return JsonResponse({"detail": str(exc)}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)

    try:
        assignment = process_webhook_result(
            provider_reference=payload.get("provider_reference", ""),
            status=payload.get("status", ""),
            raw_score=payload.get("raw_score", ""),
            summary=payload.get("summary", ""),
            detail=payload.get("detail"),
        )
    except WebhookProcessingError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({"detail": "Processed.", "assignment_id": assignment.id}, status=200)
