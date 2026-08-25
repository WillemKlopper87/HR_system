from __future__ import annotations

from rbac_audit.drf import get_request_employee, int_query_param
from rest_framework import viewsets

from .models import CriticalPost, SuccessionCandidate
from .permissions import CriticalPostPermission, SuccessionCandidatePermission
from .serializers import CriticalPostSerializer, SuccessionCandidateSerializer


class CriticalPostViewSet(viewsets.ModelViewSet):
    """Which establishment.Position posts are succession-critical (spec
    §5.1). Read is the same audience Position itself is readable to;
    write is hr_admin only."""

    queryset = CriticalPost.objects.select_related("position", "flagged_by").all()
    serializer_class = CriticalPostSerializer
    permission_classes = [CriticalPostPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        position_id = int_query_param(self.request, "position")
        if position_id is not None:
            queryset = queryset.filter(position_id=position_id)
        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(active=active.lower() in ("1", "true", "yes"))
        return queryset

    def perform_create(self, serializer):
        serializer.save(flagged_by=get_request_employee(self.request))


class SuccessionCandidateViewSet(viewsets.ModelViewSet):
    """Successor nominations against a critical post (spec §5.2). hr_admin
    only manages this; hr_admin and auditor may read it. No other role --
    including the nominated employee themself and their line_manager --
    may reach a read at all (spec §2.6)."""

    queryset = SuccessionCandidate.objects.select_related(
        "critical_post", "critical_post__position", "employee", "nominated_by"
    ).all()
    serializer_class = SuccessionCandidateSerializer
    permission_classes = [SuccessionCandidatePermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        critical_post_id = int_query_param(self.request, "critical_post")
        if critical_post_id is not None:
            queryset = queryset.filter(critical_post_id=critical_post_id)
        employee_id = int_query_param(self.request, "employee")
        if employee_id is not None:
            queryset = queryset.filter(employee_id=employee_id)
        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(active=active.lower() in ("1", "true", "yes"))

        # "No self-scope carve-out anywhere" (spec §2.6) is enforced here,
        # not just left to the frontend hiding its own UI: even an hr_admin
        # or auditor acting on their own login cannot read a row about
        # themself through this endpoint. A row this excludes simply never
        # appears in the list, and 404s (not 403s) on direct retrieve --
        # the same "filtered out of the queryset" shape row-scoping already
        # uses elsewhere (e.g. ChecklistInstance).
        actor = get_request_employee(self.request)
        if actor is not None:
            queryset = queryset.exclude(employee_id=actor.id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(nominated_by=get_request_employee(self.request))
