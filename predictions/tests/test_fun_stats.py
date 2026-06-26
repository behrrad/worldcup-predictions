"""Tests for the league fun-stats builder (predictions/fun_stats.py)."""
from django.test import TestCase

from predictions import fun_stats
from predictions.models import Membership, Prediction
from .factories import join, make_competition, make_league, make_match


class FunStatsTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.league = make_league(self.comp)
        self.a = Membership.objects.get(league=self.league, user=self.league.owner)
        self.b = join(self.league)
        self.c = join(self.league)

    def test_league_with_no_members_has_no_data(self):
        empty = make_league(self.comp, name="لیگ خالی")
        # owner is auto-added as a member, so remove them to get a truly empty league
        Membership.objects.filter(league=empty).delete()
        out = fun_stats.build_fun_stats(empty, empty.owner.id)
        self.assertFalse(out["has_data"])

    def test_no_predictions_has_no_data(self):
        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertFalse(out["has_data"])

    def test_mixed_predictors_do_not_crash(self):
        """Regression: a member with zero predictions alongside members with
        predictions must not raise ZeroDivisionError (best_buddies used to
        pollute the by_member defaultdict with empty lists)."""
        m1 = make_match(self.comp)
        Prediction.objects.create(membership=self.a, match=m1, predicted_home=1, predicted_away=0)
        # b and c never predict.
        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertTrue(out["has_data"])
        # Non-predicting members still show up in "most active" with count 0.
        zero = [r for r in out["most_active"] if r["count"] == 0]
        self.assertEqual(len(zero), 2)

    def test_full_shape_and_values(self):
        m1 = make_match(self.comp)
        m2 = make_match(self.comp)
        Prediction.objects.create(membership=self.a, match=m1, predicted_home=1, predicted_away=1)  # draw
        Prediction.objects.create(membership=self.a, match=m2, predicted_home=4, predicted_away=0)  # bold
        Prediction.objects.create(membership=self.b, match=m1, predicted_home=1, predicted_away=1)  # twins with a on m1
        Prediction.objects.create(membership=self.c, match=m2, predicted_home=2, predicted_away=2)

        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertTrue(out["has_data"])
        self.assertEqual(out["total_predictions"], 4)
        self.assertEqual(out["member_count"], 3)
        self.assertEqual(out["total_matches"], 2)

        for key in ("most_active", "dream_goals", "lone_wolf", "best_buddies",
                    "draw_kings", "crowd_favorites", "sheep_goat", "boldest"):
            self.assertIn(key, out)

        ma = {r["name"]: r["count"] for r in out["most_active"]}
        self.assertEqual(ma[self.a.user.public_name], 2)

        dk = {r["name"]: r["count"] for r in out["draw_kings"]}
        self.assertEqual(dk[self.a.user.public_name], 1)

        # a & b agreed on their only shared match -> 100%.
        pair = out["best_buddies"][0]
        self.assertEqual(pair["pct"], 100.0)
        self.assertEqual(pair["match_count"], 1)
        self.assertEqual(pair["total"], 1)

        # Viewer flagging.
        self.assertTrue(
            any(r["is_me"] for r in out["most_active"]
                if r["name"] == self.a.user.public_name)
        )
