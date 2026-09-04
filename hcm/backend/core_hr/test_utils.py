"""Shared test helpers. core_hr is the shared kernel, and test modules are
exempt from the peer-app-import boundary rule enforced by
rbac_audit/test_module_boundaries.py, so any app's tests may import from
here."""
from __future__ import annotations

from contextlib import contextmanager

from django.core.signals import request_finished
from django.db import close_old_connections


@contextmanager
def _close_old_connections_disconnected():
    request_finished.disconnect(close_old_connections)
    try:
        yield
    finally:
        request_finished.connect(close_old_connections)


def read_streaming_response(response) -> bytes:
    """Fully reads and safely closes a StreamingHttpResponse/FileResponse
    returned by the Django test client (a download-style view hit via
    self.client.get(...)).

    Works around a Django bug (ticket #35618, closed as a duplicate of
    #30448, still present as of Django 5.2): HttpResponseBase.close()
    sends the request_finished signal, which close_old_connections() is
    connected to. Inside a TestCase's wrapping atomic() block that closes
    the REAL PostgreSQL connection out from under the test --
    close_if_unusable_or_obsolete() sees get_autocommit() is False (we're
    mid-transaction) mismatched against the AUTOCOMMIT=True the settings
    expect, and unconditionally closes -- so every later query in this
    test, and in whichever test happens to run next in the same worker,
    fails with "the connection is closed". SQLite never surfaces this
    (closing and lazily reopening a SQLite connection is harmless enough
    that the inconsistency stays invisible), which is exactly why this
    was only ever seen against the Postgres CI job.

    Always use this instead of reading `response.streaming_content` and
    calling `response.close()` directly on a streamed test-client
    response."""
    content = b"".join(response.streaming_content)
    with _close_old_connections_disconnected():
        response.close()
    return content
