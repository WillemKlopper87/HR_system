# ADR-001: Backend framework — Django + Django REST Framework

**Status:** Accepted (ratified 2026-08-12; scaffolded on Django 6.1)

## Context
The sprint plan left the backend open ("Django/Laravel/Node") while mandating a modular monolith, single PostgreSQL database, and a shared RBAC + audit layer. Sprint 0 requires a chosen framework to scaffold.

## Decision
Django 5 with Django REST Framework, structured as one project with one Django app per domain module (`core_hr`, `rbac_audit`, `recruitment`, …).

## Rationale
- Django admin gives HR admins a supervised fallback UI for free from Sprint 1.
- First-class migrations support the strict FK discipline the plan requires.
- Mature ecosystem for this system's hard parts: `django-simple-history` (change audit), object/field-level permissions, Celery (background jobs, report generation).
- Python keeps the optional Sprint 12 AI summarization in the same language.

## Consequences
- Team needs Python/Django proficiency; frontend stays React (TypeScript).
- App-per-module import rules must be enforced by convention/review (see `Architecture-Design.md` §4).
