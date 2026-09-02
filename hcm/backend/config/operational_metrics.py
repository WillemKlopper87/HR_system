from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

PREFIX = "ops_metrics:v1"
API_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OTHER")
STATUS_CLASSES = ("2xx", "3xx", "4xx", "5xx")
NOTIFICATION_OUTCOMES = ("attempt", "success", "failure")
INTEGRATION_OUTCOMES = ("attempt", "success", "failure", "skipped")


def tracked_tasks() -> tuple[str, ...]:
    scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    scheduled.add("integrations.tasks.sync_collab_ids_task")
    return tuple(sorted(scheduled))


def _key(*parts: str) -> str:
    return ":".join((PREFIX, *parts))


def _increment(key: str, amount: int = 1) -> None:
    try:
        cache.add(key, 0, timeout=None)
        cache.incr(key, amount)
    except Exception:  # metrics must never break an application request/task
        logger.exception("operational metric increment failed")


def _set(key: str, value: int) -> None:
    try:
        cache.set(key, value, timeout=None)
    except Exception:
        logger.exception("operational metric timestamp write failed")


def _get_int(key: str) -> int:
    try:
        return int(cache.get(key, 0) or 0)
    except Exception:
        logger.exception("operational metric read failed")
        return 0


def record_api_request(*, method: str, status_code: int, duration_seconds: float) -> None:
    method = method if method in API_METHODS[:-1] else "OTHER"
    status_class = f"{status_code // 100}xx"
    if status_class not in STATUS_CLASSES:
        status_class = "5xx"
    _increment(_key("api", "requests", method, status_class))
    _increment(_key("api", "latency_microseconds"), max(0, round(duration_seconds * 1_000_000)))
    _increment(_key("api", "latency_count"))


def record_task(task_name: str, outcome: str) -> None:
    if task_name not in tracked_tasks() or outcome not in ("success", "failure"):
        return
    _increment(_key("task", task_name, outcome))
    _set(_key("task", task_name, f"last_{outcome}"), int(time.time()))


def record_notification_email(outcome: str) -> None:
    if outcome in NOTIFICATION_OUTCOMES:
        _increment(_key("notification", "email", outcome))
        if outcome == "failure":
            _set(_key("notification", "email", "last_failure"), int(time.time()))


def record_integration(integration: str, outcome: str) -> None:
    if integration != "collab" or outcome not in INTEGRATION_OUTCOMES:
        return
    _increment(_key("integration", integration, outcome))
    _set(_key("integration", integration, f"last_{outcome}"), int(time.time()))


def render_prometheus() -> str:
    lines = [
        "# HELP hcm_api_requests_total API requests by method and status class.",
        "# TYPE hcm_api_requests_total counter",
    ]
    for method in API_METHODS:
        for status_class in STATUS_CLASSES:
            value = _get_int(_key("api", "requests", method, status_class))
            lines.append(f'hcm_api_requests_total{{method="{method}",status_class="{status_class}"}} {value}')
    latency_us = _get_int(_key("api", "latency_microseconds"))
    lines.extend([
        "# HELP hcm_api_request_duration_seconds Aggregate API request duration.",
        "# TYPE hcm_api_request_duration_seconds summary",
        f"hcm_api_request_duration_seconds_sum {latency_us / 1_000_000:.6f}",
        f'hcm_api_request_duration_seconds_count {_get_int(_key("api", "latency_count"))}',
        "# HELP hcm_background_task_runs_total Tracked background task outcomes.",
        "# TYPE hcm_background_task_runs_total counter",
    ])
    for task_name in tracked_tasks():
        for outcome in ("success", "failure"):
            lines.append(
                f'hcm_background_task_runs_total{{task="{task_name}",outcome="{outcome}"}} '
                f'{_get_int(_key("task", task_name, outcome))}'
            )
        lines.append(
            f'hcm_background_task_last_success_timestamp_seconds{{task="{task_name}"}} '
            f'{_get_int(_key("task", task_name, "last_success"))}'
        )
        lines.append(
            f'hcm_background_task_last_failure_timestamp_seconds{{task="{task_name}"}} '
            f'{_get_int(_key("task", task_name, "last_failure"))}'
        )
    lines.extend([
        "# HELP hcm_notification_email_total Notification email delivery outcomes.",
        "# TYPE hcm_notification_email_total counter",
    ])
    for outcome in NOTIFICATION_OUTCOMES:
        lines.append(
            f'hcm_notification_email_total{{outcome="{outcome}"}} '
            f'{_get_int(_key("notification", "email", outcome))}'
        )
    lines.append(
        "hcm_notification_email_last_failure_timestamp_seconds "
        f'{_get_int(_key("notification", "email", "last_failure"))}'
    )
    lines.extend([
        "# HELP hcm_integration_sync_total Integration synchronization outcomes.",
        "# TYPE hcm_integration_sync_total counter",
    ])
    for outcome in INTEGRATION_OUTCOMES:
        lines.append(
            f'hcm_integration_sync_total{{integration="collab",outcome="{outcome}"}} '
            f'{_get_int(_key("integration", "collab", outcome))}'
        )
        lines.append(
            f'hcm_integration_last_{outcome}_timestamp_seconds{{integration="collab"}} '
            f'{_get_int(_key("integration", "collab", f"last_{outcome}"))}'
        )
    return "\n".join(lines) + "\n"
