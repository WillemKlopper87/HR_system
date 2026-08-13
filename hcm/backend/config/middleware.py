class ContentSecurityPolicyMiddleware:
    """Django's SecurityMiddleware sets X-Content-Type-Options/Referrer-
    Policy/Cross-Origin-Opener-Policy by default and XFrameOptionsMiddleware
    sets X-Frame-Options — but neither sets Content-Security-Policy, which
    Django has no built-in setting for. A minimal baseline here rather than
    adding django-csp for one header: 'self'-only by default, no framing
    (redundant with X-Frame-Options: DENY, kept for the browsers that only
    honour one or the other), no plugins. 'unsafe-inline' on script/style
    is a deliberate, documented compromise — the built-in Django admin
    (ADR-001's "free HR-admin fallback UI") uses some inline script/style
    that a stricter nonce-based policy would need admin template
    overrides to accommodate; tightening this further is a follow-up, not
    a regression versus today's total absence of a CSP header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
        )
        return response
