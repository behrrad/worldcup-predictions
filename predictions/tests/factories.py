"""Small helpers to build test data without boilerplate."""
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from predictions import consts
from predictions.models import (
    Competition,
    League,
    Match,
    Membership,
    Team,
)

_counter = {"n": 0}


def _uid():
    _counter["n"] += 1
    return _counter["n"]


def make_user(email=None, **kw):
    email = email or f"user{_uid()}@test.com"
    return User.objects.create_user(email=email, password="pw", **kw)


def make_competition(name="جام تست", **kw):
    return Competition.objects.create(name=name, **kw)


def make_team(competition, name=None, **kw):
    name = name or f"تیم {_uid()}"
    return Team.objects.create(competition=competition, name_fa=name, **kw)


def make_match(competition, home=None, away=None, kickoff=None,
               stage=consts.Stage.GROUP, **kw):
    home = home or make_team(competition)
    away = away or make_team(competition)
    kickoff = kickoff or (timezone.now() + timedelta(days=1))
    return Match.objects.create(
        competition=competition, home_team=home, away_team=away,
        kickoff=kickoff, stage=stage, **kw,
    )


def make_league(competition, owner=None, name="لیگ تست", **kw):
    owner = owner or make_user()
    league = League.objects.create(
        name=name, competition=competition, owner=owner, **kw
    )
    Membership.objects.get_or_create(
        league=league, user=owner, defaults={"role": consts.Role.OWNER}
    )
    return league


def join(league, user=None, role=consts.Role.MEMBER):
    user = user or make_user()
    return Membership.objects.create(league=league, user=user, role=role)
