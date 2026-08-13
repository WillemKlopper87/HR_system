from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .chunking import chunk_text
from .extraction import UnsupportedDocumentError, extract_text
from .models import Policy, PolicyAcknowledgment, PolicyChunk


class PolicyWorkflowError(ValueError):
    pass


def _extract_or_raise(file) -> str:
    try:
        text = extract_text(file)
    except UnsupportedDocumentError as exc:
        raise PolicyWorkflowError(str(exc)) from exc
    if not text:
        raise PolicyWorkflowError(
            "No text could be extracted from that document — a scanned/image-only PDF isn't supported yet."
        )
    return text


def _regenerate_chunks(policy: Policy) -> None:
    """Recomputes PolicyChunk rows from the policy's current body — the
    passages a future chatbot phase would embed and retrieve over. Cheap
    enough at policy-document scale to always recompute rather than diff;
    called whenever `body` is set or changed (create_policy,
    create_new_version, update_draft)."""
    policy.chunks.all().delete()
    PolicyChunk.objects.bulk_create([
        PolicyChunk(policy=policy, sequence=i, text=text)
        for i, text in enumerate(chunk_text(policy.body))
    ])


def create_policy(
    *, title: str, category: str, body: str = "", file=None, effective_date=None, actor=None
) -> Policy:
    """Either `body` is typed directly or `file` (a PDF/DOCX/TXT upload)
    is extracted into it — if both are given, the file wins, since an
    uploaded document is the authoritative source once provided."""
    code = slugify(title)[:80]
    if not code:
        raise PolicyWorkflowError("Title must produce a non-empty code.")
    if file is not None:
        body = _extract_or_raise(file)

    policy = Policy.objects.create(
        code=code, title=title, category=category, body=body,
        version=1, status=Policy.Status.DRAFT, effective_date=effective_date, created_by=actor,
    )
    if file is not None:
        policy.source_file = file
        policy.save(update_fields=["source_file"])
    _regenerate_chunks(policy)
    return policy


def create_new_version(
    policy: Policy, *, title=None, category=None, body=None, file=None, effective_date=None, actor=None
) -> Policy:
    """Drafts the next version under the SAME code, regardless of the
    source policy's own status — a published or an archived policy can
    both be revised. `version` is server-computed here, never
    client-trusted, mirroring ee_reporting.generate_report's versioning."""
    next_version = Policy.objects.filter(code=policy.code).count() + 1
    new_body = policy.body if body is None else body
    if file is not None:
        new_body = _extract_or_raise(file)

    new_policy = Policy.objects.create(
        code=policy.code,
        title=title if title is not None else policy.title,
        category=category if category is not None else policy.category,
        body=new_body,
        version=next_version,
        status=Policy.Status.DRAFT,
        effective_date=effective_date if effective_date is not None else policy.effective_date,
        created_by=actor,
    )
    if file is not None:
        new_policy.source_file = file
        new_policy.save(update_fields=["source_file"])
    _regenerate_chunks(new_policy)
    return new_policy


def update_draft(policy: Policy, *, title=None, category=None, body=None, file=None, effective_date=None) -> Policy:
    """Applies a direct PATCH to a DRAFT policy (services-layer
    counterpart to a plain edit, as opposed to create_new_version's
    explicit revision) — re-extracts text if a new file is uploaded, and
    always resyncs PolicyChunk afterward. The single source of truth for
    "only a draft can be edited directly" — see views.py::
    PolicyViewSet.perform_update."""
    if policy.status != Policy.Status.DRAFT:
        raise PolicyWorkflowError("Only a draft policy can be edited directly — publish a new version instead.")

    if file is not None:
        body = _extract_or_raise(file)
        policy.source_file = file
    if title is not None:
        policy.title = title
    if category is not None:
        policy.category = category
    if body is not None:
        policy.body = body
    if effective_date is not None:
        policy.effective_date = effective_date
    policy.save()
    _regenerate_chunks(policy)
    return policy


@transaction.atomic
def publish_policy(policy: Policy, *, actor=None) -> Policy:
    if policy.status != Policy.Status.DRAFT:
        raise PolicyWorkflowError("Only a draft policy can be published.")
    Policy.objects.filter(code=policy.code, status=Policy.Status.PUBLISHED).update(status=Policy.Status.ARCHIVED)
    policy.status = Policy.Status.PUBLISHED
    policy.published_by = actor
    policy.published_at = timezone.now()
    policy.save(update_fields=["status", "published_by", "published_at"])
    return policy


def archive_policy(policy: Policy, *, actor=None) -> Policy:
    if policy.status != Policy.Status.PUBLISHED:
        raise PolicyWorkflowError(
            "Only a published policy can be archived this way — discard an unwanted draft instead."
        )
    policy.status = Policy.Status.ARCHIVED
    policy.save(update_fields=["status"])
    return policy


def acknowledge_policy(policy: Policy, *, employee) -> PolicyAcknowledgment:
    """Idempotent by design (get_or_create, not create) — re-submitting an
    acknowledgment for the same already-acknowledged version is a no-op,
    not a 400, since the client has no reason to know it already
    succeeded (e.g. a page refresh after the request landed)."""
    if policy.status != Policy.Status.PUBLISHED:
        raise PolicyWorkflowError("Only a published policy can be acknowledged.")
    ack, _created = PolicyAcknowledgment.objects.get_or_create(employee=employee, policy=policy)
    return ack
