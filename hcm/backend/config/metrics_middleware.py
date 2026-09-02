from __future__ import annotations

from time import perf_counter

from .operational_metrics import record_api_request


class OperationalMetricsMiddleware:
    """Low-cardinality API counters; never records paths, users or payloads."""

    EXCLUDED_PATHS = {"/healthz", "/readyz", "/metrics"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = perf_counter()
        response = self.get_response(request)
        if request.path.startswith("/api/") and request.path not in self.EXCLUDED_PATHS:
            record_api_request(
                method=request.method,
                status_code=response.status_code,
                duration_seconds=perf_counter() - started,
            )
        return response
