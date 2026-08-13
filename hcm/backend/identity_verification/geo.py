from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000

# Documented constant rather than a configurable setting for now — the
# user's own "policy section" request (attendance/leave/etc. policy
# documents with acknowledgment tracking) is queued as its own future
# sprint; once it exists, this radius and the required-days-per-week
# threshold below belong there instead of hardcoded here.
OFFICE_GEOFENCE_RADIUS_M = 200
REQUIRED_OFFICE_DAYS_PER_WEEK = 2


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
