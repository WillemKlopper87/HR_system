from __future__ import annotations

import hashlib
import hmac
import time

from django.conf import settings

# Architecture-Design.md §6: "Webhook endpoints (assessment provider) are
# versioned separately, HMAC-signature-verified with replay protection
# (gap I4)." Real webhook retries are expected and should succeed as
# no-ops (see services.py::process_webhook_result's idempotency), so
# replay protection here is a bounded staleness window on the signed
# timestamp rather than a persisted nonce store — adequate at this
# system's scale (pilot-size org, no real provider under contract yet).
REPLAY_WINDOW_SECONDS = 5 * 60


class WebhookVerificationError(ValueError):
    pass


def sign_payload(raw_body: bytes, *, timestamp: int) -> str:
    secret = settings.ASSESSMENT_WEBHOOK_SECRET.encode()
    message = f"{timestamp}.".encode() + raw_body
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, *, signature: str, timestamp: str) -> None:
    if not signature or not timestamp:
        raise WebhookVerificationError("Missing signature or timestamp header.")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Timestamp header is not a valid integer.") from exc

    if abs(time.time() - timestamp_int) > REPLAY_WINDOW_SECONDS:
        raise WebhookVerificationError("Timestamp outside the allowed replay window.")

    expected = sign_payload(raw_body, timestamp=timestamp_int)
    if not hmac.compare_digest(expected, signature):
        raise WebhookVerificationError("Signature does not match.")
