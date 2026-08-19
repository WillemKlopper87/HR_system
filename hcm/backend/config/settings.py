"""
Django settings for the Sentech HCM system.

Environment-driven (12-factor): all deployment-specific values come from env
vars, with safe development defaults. See ../.env.example.
Architecture baseline: modular monolith, one PostgreSQL database
(HR_system/Architecture-Design.md, ADR-001/ADR-005).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-me",  # overridden in staging/prod
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# Django 4+ CSRF checks the browser's Origin header against this list (in
# addition to ALLOWED_HOSTS) whenever the request didn't arrive same-origin
# at the network level — which is exactly the dev shape here: the browser's
# origin is the Vite dev server (localhost:5173), proxied server-side to
# this app on :8000. Without this, every mutating request 403s with "CSRF
# Failed: Origin checking failed" even though the session/CSRF cookies are
# correct. Staging/prod serve frontend + API from one origin behind the
# reverse proxy (ADR-005) so this only needs dev's split-port shape.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get(
        "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "simple_history",
    # domain modules (one Django app per module — ADR-001).
    "core_hr",
    "rbac_audit",
    "recruitment",
    "performance",
    "learning",
    "compensation",
    "assessments",
    "identity_verification",
    "ee_reporting",
    "policies",
    "integrations",
    "notifications",
    # third-party (OpenAPI schema generation, H3)
    "drf_spectacular",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.ContentSecurityPolicyMiddleware",
    # records the acting user on every simple-history change record
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL when POSTGRES_HOST is set (compose/staging/prod);
# SQLite fallback for zero-config local checks and CI unit runs.
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "hcm"),
            "USER": os.environ.get("POSTGRES_USER", "hcm"),
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # SQLITE_PATH lets the Playwright e2e runner use its own throwaway
            # database (frontend/e2e/backend-server.mjs) instead of the dev one.
            "NAME": os.environ.get("SQLITE_PATH") or (BASE_DIR / "db.sqlite3"),
            # The threaded dev server + a browser firing parallel requests hit
            # SQLite's classic "database is locked": a DEFERRED transaction that
            # has already read cannot wait to upgrade to a write lock and fails
            # immediately, ignoring the busy timeout. IMMEDIATE takes the write
            # lock up front (and then honours the timeout). Surfaced by the H2
            # Playwright suite as an intermittent 500 on TOTP enrolment; Postgres
            # (production) is unaffected.
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    # Deny-by-default: every endpoint must opt in through the shared
    # RBAC permission classes built in Sprint 2 (rbac_audit app).
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        # OIDC/Entra ID auth added per ADR-004 (mock provider in dev)
    ],
    # Only the credential-bearing endpoints opt in (rbac_audit/throttling.py);
    # no default throttle on the rest of the API.
    "DEFAULT_THROTTLE_RATES": {
        "login_burst": os.environ.get("THROTTLE_LOGIN_BURST", "30/min"),
        "login_sustained": os.environ.get("THROTTLE_LOGIN_SUSTAINED", "500/hour"),
        "login_username": os.environ.get("THROTTLE_LOGIN_USERNAME", "10/min"),
        "totp_burst": os.environ.get("THROTTLE_TOTP_BURST", "5/min"),
        "totp_sustained": os.environ.get("THROTTLE_TOTP_SUSTAINED", "30/hour"),
    },
    "DEFAULT_PAGINATION_CLASS": "config.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    # OpenAPI schema generation (H3) — drf-spectacular introspects every
    # viewset/serializer for the schema at /api/schema/; the ~7 endpoints
    # that return a computed dict instead of a serialized model (dashboard
    # views) are annotated individually with @extend_schema where they live.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# hr_admin only — this is operational/developer tooling (the schema exposes
# every field name and endpoint shape in one place), not an employee-facing
# feature, so it gets the same access bar as the rest of the app's internal
# surfaces rather than being open to any authenticated user.
SPECTACULAR_SETTINGS = {
    "TITLE": "Sentech HCM API",
    "DESCRIPTION": "Django + DRF backend for the Sentech HCM system. See hcm/README.md for module docs.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# policies.Policy.source_file (Policy library document upload) is this
# app's first use of file storage — local disk for dev/pilot scale;
# production would move this to S3/Azure Blob (ADR-005-style deferral,
# same as everything else in this codebase that names a real vendor as a
# later decision rather than building it now).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Default (2.5MB) is too small for a realistic policy PDF.
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (throttle counters, later: reference-data caching) -----------------
# Redis when available so every gunicorn worker/celery process shares one
# view of the throttle counters; per-process LocMem otherwise (dev/tests).
if os.environ.get("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
            "KEY_PREFIX": "hcm",
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "hcm"}}

# --- Collab platform integration (ADR-011) -----------------------------------
# Outbound only, best-effort: the HCM pushes per-employee to-dos and critical
# announcements to the internal collaboration platform (integrations/collab.py).
# Off unless COLLAB_ENABLED=1 *and* both URL and key are set; the code path
# then degrades to "log and continue" if the platform is unreachable.
COLLAB_ENABLED = os.environ.get("COLLAB_ENABLED", "0") == "1"
COLLAB_BASE_URL = os.environ.get("COLLAB_BASE_URL", "")
COLLAB_API_KEY = os.environ.get("COLLAB_API_KEY", "")
COLLAB_TIMEOUT_SECONDS = float(os.environ.get("COLLAB_TIMEOUT_SECONDS", "10"))
# Absolute base URL of *this* SPA, used for deep links inside pushed items
# (e.g. https://hcm.sentech.local/my-performance).
HCM_PUBLIC_URL = os.environ.get("HCM_PUBLIC_URL", "http://localhost:5173").rstrip("/")

# --- Email adapter (H3, notifications/services.py) ---------------------------
# SMTP, not Graph -- sufficient for the demo's own domain and every consumer
# H3 wires (comp approvals, review launch, policy publish, liveness flag,
# EE sign-off); a Graph-specific backend is a drop-in EMAIL_BACKEND swap
# later, not a redesign, since callers only ever see notifications.notify().
# No SMTP_HOST set (local dev/tests/CI) => console backend, so nothing ever
# blocks on a real mail server and every send is visible in the log instead.
if os.environ.get("SMTP_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["SMTP_HOST"]
    EMAIL_PORT = int(os.environ.get("SMTP_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("SMTP_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "hcm-noreply@sentech.example.com")

# --- Celery (ADR-005: web + worker + beat + Redis) ---------------------------
# Broker/result backend come from REDIS_URL (docker-compose sets it). With no
# REDIS_URL — local `runserver`, unit tests, CI's SQLite job — tasks run
# eagerly in-process so nothing silently queues into a broker that isn't
# there. Set CELERY_TASK_ALWAYS_EAGER=0 explicitly to force broker mode.
_REDIS_URL = os.environ.get("REDIS_URL", "")
CELERY_BROKER_URL = _REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = _REDIS_URL or "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0" if _REDIS_URL else "1") == "1"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 15 * 60
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
# Scheduled jobs. Retention (rbac_audit.RetentionRule executor) is the first;
# the performance-agreement reminder job (ADR-011) will be the second.
CELERY_BEAT_SCHEDULE = {
    "run-retention-daily": {
        "task": "rbac_audit.tasks.run_retention_task",
        "schedule": 24 * 60 * 60,  # daily; crontab(hour=2) once beat runs against a real broker
    },
    # Performance-contracting reminders (PC-1/ADR-011): works out which offset
    # falls today for the open phase and pushes to-dos/digests/announcements.
    # Idempotent (ReminderLog), so a double run is harmless.
    "run-performance-reminders-daily": {
        "task": "performance.tasks.run_performance_reminders_task",
        "schedule": 24 * 60 * 60,  # daily 07:00 SAST once beat has a real broker (crontab)
    },
}

# HMAC signing secret for the inbound assessment-provider webhook
# (Architecture-Design.md §6: "HMAC-signature-verified with replay
# protection"). A real provider integration would use a per-provider
# secret issued by that vendor; kept here as one env-sourced value since
# no real provider is under contract yet (Sprint-0-Decision-Log.md A4).
ASSESSMENT_WEBHOOK_SECRET = os.environ.get(
    "ASSESSMENT_WEBHOOK_SECRET",
    "dev-only-insecure-webhook-secret-change-me",
)

# Security hardening applied whenever DEBUG is off. TLS terminates at the
# edge (nginx / load balancer, ADR-005) and nginx forwards X-Forwarded-Proto —
# without SECURE_PROXY_SSL_HEADER the SSL redirect below would loop forever
# because gunicorn only ever sees plain http from the proxy.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

# --- Logging + error tracking (H3 ops/observability) -------------------------
# Plain stdlib logging to stderr — every gunicorn/Celery deployment already
# captures that, so this needs no new infrastructure. Level is env-tunable
# so debugging one noisy module doesn't require a code change.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        # Explicit so raising the root level to quiet a noisy module can
        # never accidentally silence Django's own 5xx tracebacks.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# Sentry is entirely optional and inert unless SENTRY_DSN is set — most
# deployments (dev, CI, a pilot with no Sentry project yet) never touch
# this block. sentry-sdk is imported inside the guard, not at module top
# level, so a venv that hasn't installed it (nothing else here requires
# it) still boots cleanly with SENTRY_DSN unset.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            # POPIA: never forward employee PII to a third-party service by default.
            send_default_pii=False,
        )
    except ImportError:
        pass
