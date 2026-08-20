"""In-app + email notifications (H3, brief §7.1 #1).

Every consumer that today either pushes only to the external collab
platform (PC reminders) or notifies nobody at all (comp approvals, review
launch, policy publish, the liveness review queue, EE sign-off) writes
through the one `notify()` call in `services.py` -- a single model and a
single delivery path for every "someone should be told" case in the app,
the same shape `integrations.collab` gives outbound pushes."""
from __future__ import annotations

from django.db import models

from core_hr.base import TimestampedModel
from core_hr.models import Employee


class Notification(TimestampedModel):
    class Kind(models.TextChoices):
        PC_REMINDER = "pc_reminder", "Performance reminder"
        COMP_APPROVAL = "comp_approval", "Compensation approval"
        REVIEW_LAUNCH = "review_launch", "Review stage opened"
        POLICY_PUBLISH = "policy_publish", "Policy published"
        LIVENESS_FLAG = "liveness_flag", "Liveness review flagged"
        EE_SIGNOFF = "ee_signoff", "Performance agreement signed"
        CONTRACT_REMINDER = "contract_reminder", "Contract expiry reminder"

    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # A frontend route, e.g. "/my-performance" -- deliberately a plain
    # string, not a generic FK, so the notification survives its subject
    # being deleted and stays a dumb, cheap-to-query read model.
    link = models.CharField(max_length=300, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.recipient.employee_number}: {self.title}"
