"""
Per-endpoint DRF throttles for abuse-prone write actions.

Each class is a ``UserRateThrottle`` (keyed by authenticated user) with a fixed
``scope``; the actual rate for that scope is configured in
``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` (see config/settings.py). Scope
names live in predictions/consts.py so they never drift between here, the
settings, and the rates.
"""
from rest_framework.throttling import UserRateThrottle

from . import consts


class PredictThrottle(UserRateThrottle):
    """Limits prediction submissions per user."""

    scope = consts.THROTTLE_SCOPE_PREDICT


class JoinLeagueThrottle(UserRateThrottle):
    """Limits league-join attempts per user."""

    scope = consts.THROTTLE_SCOPE_JOIN


# `@throttle_classes` *replaces* the DEFAULT_THROTTLE_CLASSES for a view, so each
# scoped view re-lists the baseline per-user throttle alongside its tighter scoped
# one. These views require auth (anonymous requests are rejected at the permission
# check before throttling runs), so no AnonRateThrottle is needed here.
PREDICT_THROTTLES = [UserRateThrottle, PredictThrottle]
JOIN_LEAGUE_THROTTLES = [UserRateThrottle, JoinLeagueThrottle]
