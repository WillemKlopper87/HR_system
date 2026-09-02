"""`notify()` is the one write path every consumer uses (H3). In-app is
unconditional (a `Notification` row always exists so the bell is always
correct); email is best-effort on top -- a broken/unconfigured mail server
must never break the caller's own transaction (comp approval, a
signature, a publish action), the same "outbound is best-effort" rule
`integrations.collab` already follows for the external push."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from core_hr.models import Employee
from rbac_audit.models import RoleAssignment
from config.operational_metrics import record_notification_email

from .models import Notification

logger = logging.getLogger(__name__)


def notify(*, recipient: Employee, kind: str, title: str, body: str = "", link: str = "", email: bool = True) -> Notification:
    notification = Notification.objects.create(
        recipient=recipient, kind=kind, title=title, body=body, link=link,
    )
    if email and recipient.work_email:
        _send_email(notification)
    return notification


def notify_many(recipients, *, kind: str, title: str, body: str = "", link: str = "", email: bool = True) -> list[Notification]:
    """Same as `notify`, batched -- policy-publish-to-everyone and similar
    broadcasts create every row in one query instead of N."""
    notifications = Notification.objects.bulk_create([
        Notification(recipient=recipient, kind=kind, title=title, body=body, link=link)
        for recipient in recipients
    ])
    if email:
        for notification in notifications:
            if notification.recipient.work_email:
                _send_email(notification)
    return notifications


def employees_with_role(role_name: str):
    """Every employee currently holding a role, for the broadcast-style
    consumers (the liveness review queue notifying hr_admin, etc.) that
    have no single natural recipient the way a signature or a proposal does."""
    return Employee.objects.filter(
        role_assignments__role__name=role_name, role_assignments__revoked_at__isnull=True,
    ).distinct()


def _send_email(notification: Notification) -> None:
    record_notification_email("attempt")
    try:
        send_mail(
            subject=f"[Sentech HCM] {notification.title}",
            message=(
                f"{notification.body}\n\n"
                f"{settings.HCM_PUBLIC_URL}{notification.link}" if notification.link else notification.body
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient.work_email],
            fail_silently=False,
        )
    except Exception:
        # A misconfigured/unreachable mail server must never break the
        # caller's own transaction -- the in-app row already exists.
        logger.exception("notification email failed for notification %s", notification.pk)
        record_notification_email("failure")
        return
    notification.emailed_at = timezone.now()
    notification.save(update_fields=["emailed_at"])
    record_notification_email("success")
