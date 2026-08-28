"""The external careers portal — the system's first genuinely public,
unauthenticated, write-capable surface (C6 design spec §2.5, §3.4). Kept in
one file, deliberately: everything AllowAny and everything a script can POST
to without a session lives here, so the entire anonymous-write surface can
be audited by reading one module rather than hunting through views.py
alongside every authenticated endpoint.

Two endpoints:
    GET  /api/v1/careers/postings/       -- list open, externally-posted requisitions
    GET  /api/v1/careers/postings/{id}/  -- one posting's detail
    POST /api/v1/careers/apply/          -- submit an application

Anti-abuse, all three layers documented in the design spec §3.4 and applied
here: throttling (rbac_audit.throttling's CAREERS_* classes), content-sniffed
resume validation (recruitment/validation.py, via services.
submit_portal_application), and a honeypot field on the application form.
"""
from __future__ import annotations

from core_hr.models import EmployeeVersion
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.throttling import CAREERS_APPLICATION_THROTTLES, CAREERS_READ_THROTTLES
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Requisition
from .services import DuplicateApplicationError, submit_portal_application


class PublicPostingSerializer(serializers.ModelSerializer):
    """Deliberately narrow — an anonymous visitor gets exactly enough to
    decide whether to apply, nothing about internal pipeline shape
    (headcount targets, hiring_manager, positions, created_by)."""

    department = serializers.CharField(source="department.name", read_only=True)
    location = serializers.CharField(source="location.name", read_only=True)
    occupational_level = serializers.CharField(source="occupational_level.name", read_only=True)

    class Meta:
        model = Requisition
        fields = [
            "id", "title", "department", "occupational_level", "location",
            "description", "target_fill_date",
        ]


class PublicPostingViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublicPostingSerializer
    permission_classes = [AllowAny]
    throttle_classes = CAREERS_READ_THROTTLES

    def get_queryset(self):
        return (
            Requisition.objects.filter(status=Requisition.Status.OPEN, external_posting=True)
            .select_related("department", "location", "occupational_level")
        )


class PublicApplicationSerializer(serializers.Serializer):
    """A plain Serializer, not a ModelSerializer — this never maps 1:1 onto
    Applicant (the honeypot field must never touch the model; consent
    handling and Source/provenance stamping are services.
    submit_portal_application's job, not this serializer's). Consent gates
    STORAGE of demographic answers, not submission of the form (design spec
    §3.4.5) -- so no validation here rejects a submission for having
    demographics without consent; that's handled by simply not persisting
    them, inside the service function."""

    requisition = serializers.PrimaryKeyRelatedField(
        queryset=Requisition.objects.filter(status=Requisition.Status.OPEN, external_posting=True)
    )
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    date_of_birth = serializers.CharField()
    resume = serializers.FileField()
    race = serializers.CharField(required=False, allow_blank=True, default="")
    gender = serializers.CharField(required=False, allow_blank=True, default="")
    disability_status = serializers.CharField(required=False, allow_blank=True, default="")
    demographic_consent = serializers.BooleanField(required=False, default=False)
    # Honeypot -- never rendered visibly on the real form, so a human never
    # fills it in; a scripted bot filling every field blindly does. Handled
    # in careers_apply below, not here, so a filled honeypot short-circuits
    # before any of this serializer's validation even runs.
    website = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_date_of_birth(self, value):
        parsed = parse_date(value)
        if parsed is None:
            raise serializers.ValidationError("Enter a valid date (YYYY-MM-DD).")
        return parsed

    def validate_race(self, value):
        # Same "not_disclosed default, self-disclosed only" posture as the
        # internal ApplicantSerializer -- an unrecognised value is silently
        # dropped (treated as not-disclosed) rather than 400ing the whole
        # application over one malformed field.
        return value if value in EmployeeVersion.Race.values else ""

    def validate_gender(self, value):
        return value if value in EmployeeVersion.Gender.values else ""

    def validate_disability_status(self, value):
        return value if value in EmployeeVersion.DisabilityStatus.values else ""


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(CAREERS_APPLICATION_THROTTLES)
def careers_apply(request):
    honeypot = str(request.data.get("website", "") or "").strip()
    if honeypot:
        # Indistinguishable from a real success to a bot that filled every
        # field blindly -- no row is created, and we don't tip it off by
        # returning a different status/shape.
        return Response({"detail": "Application received."}, status=201)

    serializer = PublicApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        applicant = submit_portal_application(
            requisition=data["requisition"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data.get("phone", ""),
            date_of_birth=data["date_of_birth"],
            resume=data["resume"],
            race=data.get("race", ""),
            gender=data.get("gender", ""),
            disability_status=data.get("disability_status", ""),
            demographic_consent=data.get("demographic_consent", False),
        )
    except DuplicateApplicationError as exc:
        return Response({"detail": str(exc)}, status=400)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)

    # No internal sequential ID in the response (HR_Code_report.md
    # lower-priority note) -- nothing on the public side tracks an
    # application by reference yet (no "track your status" feature exists),
    # so there's nothing to justify exposing it for.
    return Response({"detail": "Application received."}, status=201)
