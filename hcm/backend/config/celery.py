"""Celery application (ADR-005 topology: web + worker + beat + Redis).

Loaded from config/__init__.py so `celery -A config worker` and
`celery -A config beat` find it, and so `@shared_task`s bind to it when
Django starts. Task modules are discovered per installed app
(`<app>/tasks.py`). Broker/result backend and the beat schedule live in
config/settings.py under the CELERY_ prefix.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("hcm")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
