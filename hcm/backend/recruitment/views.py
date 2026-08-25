from __future__ import annotations

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.consent import record_consent
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import can_see_unsuppressed_aggregates, has_role
from rbac_audit.tiers import FieldTier
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .models import (
    Applicant,
    ApplicantStageEvent,
    BackgroundCheck,
    InterviewScorecard,
    InterviewSession,
    Offer,
    Requisition,
)
from .permissions import (
    InterviewScorecardPermission,
    IsRecruiterOrHRAdmin,
    IsRecruiterOrHRAdminOrAssignedInterviewer,
)
from .serializers import (
    ApplicantSerializer,
    ApplicantStageEventSerializer,
    BackgroundCheckSerializer,
    InterviewScorecardSerializer,
    InterviewSessionSerializer,
    OfferSerializer,
    RequisitionSerializer,
)
from .services import StageTransitionError, transition_applicant

SMALL_CELL_THRESHOLD = 5


class RequisitionViewSet(viewsets.ModelViewSet):
    queryset = Requisition.objects.select_related(
        "department", "occupational_level", "job_grade", "location", "hiring_manager", "created_by"
    )
    serializer_class = RequisitionSerializer
    permission_classes = [IsRecruiterOrHRAdmin]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=get_request_employee(self.request))
        self._stamp_status_dates(instance, previous_status=None)

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        self._stamp_status_dates(instance, previous_status=previous_status)

    @staticmethod
    def _stamp_status_dates(instance: Requisition, *, previous_status):
        update_fields = []
        if instance.status == Requisition.Status.OPEN and instance.opened_at is None:
            instance.opened_at = timezone.localdate()
            update_fields.append("opened_at")
        if instance.status == Requisition.Status.CLOSED and previous_status != Requisition.Status.CLOSED:
            instance.closed_at = timezone.localdate()
            update_fields.append("closed_at")
        if update_fields:
            instance.save(update_fields=update_fields)


class ApplicantViewSet(viewsets.ModelViewSet):
    """No DELETE — applicants leave the pipeline via the 'rejected' stage,
    not row deletion, so the audit trail (stage_events, consent_records)
    always stays attached to something real."""

    queryset = Applicant.objects.select_related("requisition", "resulting_employee")
    serializer_class = ApplicantSerializer
    permission_classes = [IsRecruiterOrHRAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=True, methods=["post"])
    def consent(self, request, pk=None):
        """purpose defaults to demographic_self_id (this action's original
        sole use) but also accepts "assessment" — assessments/services.py's
        consent gate for applicant-subject assignments can't capture
        consent itself (it must not import recruitment.Applicant; see
        assessments/models.py's AssessmentAssignment docstring), so it
        points callers back at this existing endpoint instead of
        duplicating consent-capture logic in a second module."""
        applicant = self.get_object()
        purpose = request.data.get("purpose", ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID)
        if purpose not in ConsentRecord.Purpose.values:
            return Response({"detail": "Invalid purpose."}, status=400)
        record_consent(
            applicant=applicant,
            purpose=purpose,
            lawful_basis=request.data.get("lawful_basis", ConsentRecord.LawfulBasis.CONSENT),
            text_version=request.data.get("text_version", "v1"),
            actor=get_request_employee(request),
        )
        return Response({"detail": "Consent recorded."}, status=201)

    @action(detail=True, methods=["get"])
    def stage_events(self, request, pk=None):
        applicant = self.get_object()
        events = applicant.stage_events.select_related("changed_by").order_by("created_at")
        return Response(ApplicantStageEventSerializer(events, many=True).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        applicant = self.get_object()
        to_stage = request.data.get("to_stage")
        if to_stage not in Applicant.Stage.values:
            return Response({"detail": "Invalid to_stage."}, status=400)
        try:
            transition_applicant(
                applicant,
                to_stage=to_stage,
                actor=get_request_employee(request),
                notes=request.data.get("notes", ""),
                rejected_reason=request.data.get("rejected_reason", ""),
            )
        except (StageTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=400)
        applicant.refresh_from_db()
        return Response(self.get_serializer(applicant).data)


class OfferViewSet(viewsets.ModelViewSet):
    queryset = Offer.objects.select_related("applicant", "proposed_job_grade", "proposed_by", "approved_by")
    serializer_class = OfferSerializer
    permission_classes = [IsRecruiterOrHRAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(proposed_by=get_request_employee(self.request))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        offer = self.get_object()
        if offer.status != Offer.Status.PROPOSED:
            return Response({"detail": "Only a proposed offer can be approved."}, status=400)
        actor = get_request_employee(request)
        # Segregation of duties (RBAC-Roles.md standing rule 4): the same
        # person can't propose and approve their own offer.
        if actor is not None and offer.proposed_by_id == actor.id:
            return Response(
                {"detail": "The proposer cannot also approve this offer (segregation of duties)."}, status=400
            )
        offer.status = Offer.Status.APPROVED
        offer.approved_by = actor
        offer.approved_at = timezone.now()
        offer.save(update_fields=["status", "approved_by", "approved_at"])
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        offer = self.get_object()
        if offer.status != Offer.Status.APPROVED:
            return Response({"detail": "Only an approved offer can be accepted."}, status=400)
        offer.status = Offer.Status.ACCEPTED
        offer.save(update_fields=["status"])
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        offer = self.get_object()
        offer.status = Offer.Status.DECLINED
        offer.save(update_fields=["status"])
        return Response(self.get_serializer(offer).data)


# --- C6: interview scheduling, panel scorecards, background checks --------

class InterviewSessionViewSet(viewsets.ModelViewSet):
    """Design spec §3.1: recruiter/hr_admin manage the whole pipeline; an
    assigned interviewer gets read-only access to sessions they're on the
    panel for, via get_queryset's row-filtering below plus
    IsRecruiterOrHRAdminOrAssignedInterviewer's object-level check."""

    queryset = InterviewSession.objects.select_related("applicant", "applicant__requisition").prefetch_related(
        "interviewers"
    )
    serializer_class = InterviewSessionSerializer
    permission_classes = [IsRecruiterOrHRAdminOrAssignedInterviewer]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        # ?mine=true forces "sessions I'm personally on the panel for"
        # regardless of role -- without it, a recruiter/hr_admin sees every
        # session (the admin view, e.g. ApplicantDetailPage); MyInterviewsPage
        # needs the row-scoped view even for a recruiter/hr_admin who is
        # ALSO occasionally a panelist, so role alone can't decide this.
        mine_only = self.request.query_params.get("mine") == "true"
        if mine_only or not (has_role(employee, "recruiter") or has_role(employee, "hr_admin")):
            qs = qs.filter(interviewers=employee)
        applicant_id = int_query_param(self.request, "applicant")
        if applicant_id is not None:
            qs = qs.filter(applicant_id=applicant_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))


class InterviewScorecardViewSet(viewsets.ModelViewSet):
    queryset = InterviewScorecard.objects.select_related("session", "interviewer", "session__applicant")
    serializer_class = InterviewScorecardSerializer
    permission_classes = [InterviewScorecardPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        if has_role(employee, "recruiter") or has_role(employee, "hr_admin"):
            pass
        else:
            # Own scorecards plus peers' on any session this employee is on
            # the panel for — to_representation (InterviewScorecardSerializer)
            # masks peer content until the viewer has submitted their own
            # (spec §2.2).
            qs = qs.filter(session__interviewers=employee).distinct()
        session_id = int_query_param(self.request, "session")
        if session_id is not None:
            qs = qs.filter(session_id=session_id)
        return qs


class BackgroundCheckViewSet(viewsets.ModelViewSet):
    """Tracking only, no vendor integration (design spec §2.3) — reuses
    IsRecruiterOrHRAdmin unchanged: the whole model is Sensitive-tier by
    nature, and that permission class's audience is already the correct
    one. No interviewer access at all, unlike InterviewSession/
    InterviewScorecard above."""

    queryset = BackgroundCheck.objects.select_related("applicant", "requested_by")
    serializer_class = BackgroundCheckSerializer
    permission_classes = [IsRecruiterOrHRAdmin]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        applicant_id = int_query_param(self.request, "applicant")
        if applicant_id is not None:
            qs = qs.filter(applicant_id=applicant_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(requested_by=get_request_employee(self.request))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated, IsRecruiterOrHRAdmin])
def recruitment_dashboard(request):
    """Sprint 4's recruitment dashboard: pipeline status, time-to-fill,
    applicant demographics — small-cell-suppressed on the same basis as
    core_hr's headcount dashboard (RBAC-Roles.md standing rule 1 / gap C6).
    Demographic values themselves are already consent-gated at the point
    of capture (ApplicantSerializer.validate) — an applicant without
    consent is still 'not_disclosed' in the database, so no extra
    filtering is needed here to keep the aggregate consent-respecting."""
    employee = get_request_employee(request)
    can_see_unsuppressed = can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)

    applicants = Applicant.objects.all()
    by_stage = list(applicants.values("current_stage").annotate(count=Count("id")).order_by("current_stage"))

    hire_events = ApplicantStageEvent.objects.filter(to_stage=Applicant.Stage.HIRED).select_related(
        "applicant__requisition"
    )
    fill_days = [
        (event.created_at.date() - event.applicant.requisition.opened_at).days
        for event in hire_events
        if event.applicant.requisition.opened_at is not None
    ]
    avg_time_to_fill_days = round(sum(fill_days) / len(fill_days), 1) if fill_days else None

    def _breakdown(field: str, *, suppress: bool):
        rows = applicants.values(field).annotate(count=Count("id")).order_by(field)
        result = []
        for row in rows:
            count = row["count"]
            is_small = suppress and count < SMALL_CELL_THRESHOLD
            result.append({
                "key": row[field],
                "count": f"<{SMALL_CELL_THRESHOLD}" if is_small else count,
                "suppressed": is_small,
            })
        return result

    data = {
        "open_requisitions": Requisition.objects.filter(status=Requisition.Status.OPEN).count(),
        "total_applicants": applicants.count(),
        "avg_time_to_fill_days": avg_time_to_fill_days,
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "by_stage": [{"key": row["current_stage"], "count": row["count"]} for row in by_stage],
        "by_race": _breakdown("race", suppress=not can_see_unsuppressed),
        "by_gender": _breakdown("gender", suppress=not can_see_unsuppressed),
        "by_disability_status": _breakdown("disability_status", suppress=not can_see_unsuppressed),
    }
    return Response(data)
