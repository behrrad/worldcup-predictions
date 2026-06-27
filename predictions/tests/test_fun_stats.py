"""Tests for the league fun-stats builder (predictions/fun_stats.py)."""
from django.test import TestCase

from predictions import consts, fun_stats
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

        # No pair reaches the shared-match floor here, so best_buddies is empty.
        self.assertEqual(out["best_buddies"], [])

        # Viewer flagging.
        self.assertTrue(
            any(r["is_me"] for r in out["most_active"]
                if r["name"] == self.a.user.public_name)
        )

    def test_best_buddies_requires_minimum_shared_matches(self):
        """A pair only qualifies once it has FUN_STATS_MIN_BUDDY_MATCHES shared
        predictions — one identical pick no longer floods the list at 100%."""
        floor = consts.FUN_STATS_MIN_BUDDY_MATCHES
        matches = [make_match(self.comp) for _ in range(floor)]

        # One short of the floor: a & b predict identically on (floor - 1) games.
        for m in matches[: floor - 1]:
            Prediction.objects.create(membership=self.a, match=m, predicted_home=1, predicted_away=1)
            Prediction.objects.create(membership=self.b, match=m, predicted_home=1, predicted_away=1)

        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertEqual(out["best_buddies"], [])

        # One more shared game crosses the floor and qualifies the pair.
        Prediction.objects.create(membership=self.a, match=matches[-1], predicted_home=2, predicted_away=0)
        Prediction.objects.create(membership=self.b, match=matches[-1], predicted_home=2, predicted_away=0)

        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertEqual(len(out["best_buddies"]), 1)
        pair = out["best_buddies"][0]
        self.assertEqual(pair["total"], floor)
        self.assertEqual(pair["match_count"], floor)
        self.assertEqual(pair["pct"], 100.0)

    def test_best_buddies_requires_active_participants(self):
        """Both members of a pair must have predicted >= 50% of the finished
        matches — a barely-active member doesn't qualify even with a perfect
        agreement rate on the games they did play."""
        ms = [make_match(self.comp) for _ in range(12)]  # bar = 6
        # a predicts all 12 (active); b predicts only the first 5 (< 6).
        for m in ms:
            Prediction.objects.create(membership=self.a, match=m, predicted_home=1, predicted_away=1)
        for m in ms[:5]:
            Prediction.objects.create(membership=self.b, match=m, predicted_home=1, predicted_away=1)
        for m in ms:
            m.home_score, m.away_score = 1, 1
            m.save()

        # a & b share 5 games (clears the shared floor) and agree on all, but b
        # predicted only 5 of 12 finished matches, so the pair is excluded.
        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertEqual(out["best_buddies"], [])

        # b predicts a sixth finished match -> exactly 50%, now active.
        Prediction.objects.create(membership=self.b, match=ms[5], predicted_home=1, predicted_away=1)
        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertEqual(len(out["best_buddies"]), 1)
        self.assertEqual(out["best_buddies"][0]["total"], 6)

    def test_buddies_unfiltered_before_any_match_finishes(self):
        """With no finished matches there's no participation signal, so the
        bar is skipped and the shared-match floor alone gates pairs."""
        floor = consts.FUN_STATS_MIN_BUDDY_MATCHES
        ms = [make_match(self.comp) for _ in range(floor)]  # none finished
        for m in ms:
            Prediction.objects.create(membership=self.a, match=m, predicted_home=0, predicted_away=0)
            Prediction.objects.create(membership=self.b, match=m, predicted_home=0, predicted_away=0)

        out = fun_stats.build_fun_stats(self.league, self.a.user_id)
        self.assertEqual(len(out["best_buddies"]), 1)
        self.assertEqual(out["best_buddies"][0]["total"], floor)
