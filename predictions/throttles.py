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
