"""
Per-endpoint DRF throttles for abuse-prone write actions.

Each class is a ``UserRateThrottle`` (keyed by authenticated user) with a fixed
``scope``; the actual rate for that scope is configured in
``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` (see config/settings.py). Scope
names live in predictions/consts.py so they never drift between here, the
settings, and the rates.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from . import consts


class PredictThrottle(UserRateThrottle):
    """Limits prediction submissions per user."""

    scope = consts.THROTTLE_SCOPE_PREDICT


class JoinLeagueThrottle(UserRateThrottle):
    """Limits league-join attempts per user."""

    scope = consts.THROTTLE_SCOPE_JOIN


class ExportThrottle(AnonRateThrottle):
    """Limits the public, key-gated results download (keyed by client IP).

    This is an anonymous endpoint, so it uses AnonRateThrottle rather than the
    per-user throttles above — there is no authenticated user to key on."""

    scope = consts.THROTTLE_SCOPE_EXPORT


class ScoreboardThrottle(AnonRateThrottle):
    """Limits anonymous reads of the public global scoreboard (keyed by client IP)."""

    scope = consts.THROTTLE_SCOPE_SCOREBOARD


# `@throttle_classes` *replaces* the DEFAULT_THROTTLE_CLASSES for a view, so each
# scoped view re-lists the baseline per-user throttle alongside its tighter scoped
# one. These views require auth (anonymous requests are rejected at the permission
# check before throttling runs), so no AnonRateThrottle is needed here.
PREDICT_THROTTLES = [UserRateThrottle, PredictThrottle]
JOIN_LEAGUE_THROTTLES = [UserRateThrottle, JoinLeagueThrottle]
# The export endpoint is public, so only the anonymous (IP-keyed) throttle applies.
EXPORT_THROTTLES = [ExportThrottle]
# The scoreboard is public too, but signed-in visitors also hit it: anonymous
# requests are IP-throttled, authenticated ones fall under the baseline per-user
# throttle (AnonRateThrottle ignores authenticated requests).
SCOREBOARD_THROTTLES = [UserRateThrottle, ScoreboardThrottle]
