from __future__ import annotations

from core_hr.permissions import IsHRAdminOrReadOnly
from django.utils import timezone
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Feedback, Goal, Review, ReviewCycle
from .serializers import FeedbackSerializer, GoalSerializer, ReviewCycleSerializer, ReviewSerializer
from .services import classify_feedback_type, close_review_cycle, launch_review_cycle


class ReviewCycleViewSet(viewsets.ModelViewSet):
    """Any authenticated employee can read cycle name/dates (Internal-tier,
    not sensitive — they need to know which cycle their review belongs
    to); only hr_admin can create/edit/launch/close, per the acceptance
    criterion ("HR admin can launch a review cycle...")."""

    queryset = ReviewCycle.objects.all()
    serializer_class = ReviewCycleSerializer
    permission_classes = [IsHRAdminOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))

    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        cycle = self.get_object()
        try:
            created = launch_review_cycle(cycle)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        cycle.refresh_from_db()
        return Response({**self.get_serializer(cycle).data, "reviews_created": created})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        cycle = self.get_object()
        try:
            close_review_cycle(cycle)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        cycle.refresh_from_db()
        return Response(self.get_serializer(cycle).data)

    @action(detail=True, methods=["get"])
    def completion(self, request, pk=None):
        cycle = self.get_object()
        reviews = cycle.reviews.all()
        total = reviews.count()
        self_submitted = reviews.filter(self_submitted_at__isnull=False).count()
        manager_submitted = reviews.filter(manager_submitted_at__isnull=False).count()
        completed = reviews.filter(self_submitted_at__isnull=False, manager_submitted_at__isnull=False).count()

        def pct(n: int) -> float:
            return round(100 * n / total, 1) if total else 0.0

        return Response({
            "total": total,
            "self_submitted": self_submitted,
            "self_submitted_pct": pct(self_submitted),
            "manager_submitted": manager_submitted,
            "manager_submitted_pct": pct(manager_submitted),
            "completed": completed,
            "completed_pct": pct(completed),
        })


class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = Goal.objects.select_related("employee", "manager", "created_by")
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))


class ReviewViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """No create/delete — Review rows only come from launch_review_cycle
    (one per employee active at launch), and stay attached to the cycle
    for its full lifecycle."""

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = Review.objects.select_related("review_cycle", "employee", "manager")
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee

    @action(detail=True, methods=["post"])
    def submit_self(self, request, pk=None):
        review = self.get_object()
        requester = get_request_employee(request)
        if requester is None or review.employee_id != requester.id:
            return Response({"detail": "Only the reviewee can submit the self-review."}, status=403)
        if review.self_rating is None:
            return Response({"detail": "Set a self rating before submitting."}, status=400)
        review.self_submitted_at = timezone.now()
        review.save(update_fields=["self_submitted_at"])
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=["post"])
    def submit_manager(self, request, pk=None):
        review = self.get_object()
        requester = get_request_employee(request)
        if requester is None or review.manager_id != requester.id:
            return Response({"detail": "Only the assigned manager can submit the manager review."}, status=403)
        if review.manager_rating is None:
            return Response({"detail": "Set a manager rating before submitting."}, status=400)
        review.manager_submitted_at = timezone.now()
        review.save(update_fields=["manager_submitted_at"])
        return Response(self.get_serializer(review).data)


class FeedbackViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """Create is open to any authenticated employee — RowScopePermission
    only gates existing objects (has_object_permission) and the list
    queryset, not creation, which is exactly right here: peer feedback
    crosses the org chart by definition. Reading is row-scoped to the
    subject (self / their manager's reporting chain / hr_admin)."""

    serializer_class = FeedbackSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]

    def get_queryset(self):
        queryset = Feedback.objects.select_related("employee", "author")
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee

    def perform_create(self, serializer):
        author = get_request_employee(self.request)
        target = serializer.validated_data["employee"]
        serializer.save(author=author, feedback_type=classify_feedback_type(author, target))
