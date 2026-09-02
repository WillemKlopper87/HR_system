from __future__ import annotations

from celery.signals import task_failure, task_success

from .operational_metrics import record_task, tracked_tasks


@task_success.connect(weak=False)
def record_task_success(sender=None, **_kwargs):
    task_name = getattr(sender, "name", "")
    if task_name in tracked_tasks():
        record_task(task_name, "success")


@task_failure.connect(weak=False)
def record_task_failure(sender=None, **_kwargs):
    task_name = getattr(sender, "name", "")
    if task_name in tracked_tasks():
        record_task(task_name, "failure")
