from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Every model in this project uses `created_at` (the TimestampedModel
    convention — see Data-Dictionary.md 'All tables: id, created_at,
    updated_at') rather than DRF's default `created` ordering field."""

    ordering = "-created_at"
