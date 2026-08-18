"""Outbound adapter for the internal collaboration platform (ADR-011).

The HCM is the system of record; this module only *pushes* — per-employee
work items and department-scoped announcements — over the collab platform's
machine-to-machine surface (`/integrations/...`, X-Api-Key), and looks up
identity mappings (`/users/by-email/`, `/departments`). It never reads back
state that would drive HCM decisions: a "done" in collab is a nudge, never a
signature.

Design points:
* **Best-effort, never blocking.** `get_client()` returns None when
  COLLAB_ENABLED is off or unconfigured; callers treat that as "log and carry
  on". Every call retries transient failures (connection errors, 5xx, 429)
  with backoff, then raises `CollabError` — callers decide whether that
  matters (the reminder job records it and moves on).
* **Idempotent by construction.** Work items are addressed by
  `(source, external_ref)`; announcements carry a `dedupe_key`; re-running a
  job re-sends the same calls and the collab side answers with the same rows.
* **Testable without a network.** `CollabClient(transport=httpx.MockTransport)`
  — see integrations/test_collab.py.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

SOURCE = "hcm"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class CollabError(RuntimeError):
    """The collab platform could not be reached or refused the request after retries."""

    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class CollabConfig:
    base_url: str
    api_key: str
    timeout: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.5

    @classmethod
    def from_settings(cls) -> "CollabConfig | None":
        if not getattr(settings, "COLLAB_ENABLED", False):
            return None
        base_url = (getattr(settings, "COLLAB_BASE_URL", "") or "").rstrip("/")
        api_key = getattr(settings, "COLLAB_API_KEY", "") or ""
        if not base_url or not api_key:
            logger.warning("COLLAB_ENABLED is on but COLLAB_BASE_URL/COLLAB_API_KEY are not set — collab push disabled")
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout=float(getattr(settings, "COLLAB_TIMEOUT_SECONDS", 10.0)),
        )


class CollabClient:
    def __init__(self, config: CollabConfig, *, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.config = config
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=config.base_url,
            headers={"X-Api-Key": config.api_key, "Accept": "application/json"},
            timeout=config.timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    # -- low level -----------------------------------------------------------

    def _request(self, method: str, path: str, *, json=None, ok=(200, 201), allow_404: bool = False):
        last: CollabError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.HTTPError as exc:
                last = CollabError(f"{method} {path}: {exc}")
            else:
                if response.status_code in ok:
                    return response.json() if response.content else None
                if allow_404 and response.status_code == 404:
                    return None
                last = CollabError(
                    f"{method} {path} -> {response.status_code}", status=response.status_code, body=response.text[:500]
                )
                if response.status_code not in RETRY_STATUSES:
                    raise last
            if attempt < self.config.max_attempts:
                self._sleep(self.config.backoff_seconds * (2 ** (attempt - 1)))
        assert last is not None
        raise last

    # -- identity mapping ----------------------------------------------------

    def lookup_user_id(self, email: str) -> str | None:
        data = self._request("GET", f"/users/by-email/{email.strip().lower()}", allow_404=True)
        return str(data["id"]) if data else None

    def list_departments(self) -> list[dict]:
        return self._request("GET", "/departments") or []

    # -- work items ----------------------------------------------------------

    def ensure_project(self, *, collab_department_id: str, name: str, description: str | None = None) -> str:
        data = self._request(
            "POST",
            "/integrations/projects/ensure",
            json={"owning_department_id": collab_department_id, "name": name, "description": description},
        )
        return str(data["id"])

    def upsert_work_item(
        self,
        external_ref: str,
        *,
        project_id: str,
        title: str,
        assignee_user_id: str | None = None,
        assignee_email: str | None = None,
        description: str | None = None,
        due_on: date | None = None,
        starts_on: date | None = None,
        priority: str = "normal",
        status: str = "todo",
    ) -> dict:
        payload = {
            "project_id": project_id,
            "title": title,
            "description": description,
            "assignee_user_id": assignee_user_id,
            "assignee_email": assignee_email,
            "due_on": due_on.isoformat() if due_on else None,
            "starts_on": starts_on.isoformat() if starts_on else None,
            "priority": priority,
            "status": status,
        }
        return self._request("PUT", f"/integrations/work-items/{SOURCE}/{external_ref}", json=payload)

    def close_work_item(self, external_ref: str, *, project_id: str, title: str, **kw) -> dict:
        return self.upsert_work_item(external_ref, project_id=project_id, title=title, status="done", **kw)

    def get_work_item(self, external_ref: str) -> dict | None:
        return self._request("GET", f"/integrations/work-items/{SOURCE}/{external_ref}", allow_404=True)

    # -- announcements -------------------------------------------------------

    def publish_announcement(
        self,
        *,
        title: str,
        body: str,
        audience_type: str = "organisation",
        audience_ref: str | None = None,
        priority: str = "info",
        requires_ack: bool = True,
        dedupe_key: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/integrations/announcements",
            json={
                "title": title,
                "body": body,
                "audience_type": audience_type,
                "audience_ref": audience_ref,
                "priority": priority,
                "requires_ack": requires_ack,
                "dedupe_key": dedupe_key,
            },
        )


def get_client(*, transport: httpx.BaseTransport | None = None) -> CollabClient | None:
    """None when the integration is disabled/unconfigured — callers log and skip."""
    config = CollabConfig.from_settings()
    if config is None:
        return None
    return CollabClient(config, transport=transport)
