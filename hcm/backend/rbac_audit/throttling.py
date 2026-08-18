"""Rate limits for the credential-bearing endpoints (H1 / brief D1).

Two threats, two keys:

* **Login** is anonymous, so it is throttled per source IP (burst + sustained)
  *and* per submitted username. IP-only limits are useless against a slow
  distributed guess at one account and, behind a corporate NAT, far too tight
  for a whole office logging in at 08:00 — the per-username limit is what
  actually protects an account.
* **TOTP confirm / step-up challenge** are authenticated, so they are keyed
  per user (burst + sustained). A 6-digit code with `valid_window=1` means
  ~3 valid codes per 30 s; the sustained cap (default 30/hour) makes an
  online brute force impractical instead of merely slow.

Rates live in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] so they are tunable
per environment without touching code. Counters use Django's default cache
(Redis when REDIS_URL is set — see settings.CACHES — so gunicorn workers
share them; LocMem otherwise).
"""
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class LoginBurstThrottle(AnonRateThrottle):
    scope = "login_burst"


class LoginSustainedThrottle(AnonRateThrottle):
    scope = "login_sustained"


class LoginUsernameThrottle(SimpleRateThrottle):
    """Keyed by the username in the POST body (lower-cased), regardless of IP."""

    scope = "login_username"

    def get_cache_key(self, request, view):
        username = ""
        try:
            username = str(request.data.get("username", "") or "").strip().lower()
        except Exception:  # noqa: BLE001 — malformed body: fall through to no throttle key
            username = ""
        if not username:
            return None
        return self.cache_format % {"scope": self.scope, "ident": username[:150]}


class TotpBurstThrottle(UserRateThrottle):
    scope = "totp_burst"


class TotpSustainedThrottle(UserRateThrottle):
    scope = "totp_sustained"


LOGIN_THROTTLES = [LoginBurstThrottle, LoginSustainedThrottle, LoginUsernameThrottle]
TOTP_THROTTLES = [TotpBurstThrottle, TotpSustainedThrottle]
