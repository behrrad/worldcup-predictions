"""Smoke tests for the (Unfold-themed) Django admin panel.

Distinct from test_admin.py, which covers the in-app /api/admin/* JSON endpoints.

`manage.py check` and the rest of the suite never render an admin page, so a
typo in a model-admin config or in an UNFOLD sidebar `reverse_lazy` link would
ship green and only 500 at request time. These tests render the key admin pages
as a superuser and assert the theme/config is actually wired.

The default staticfiles backend is WhiteNoise's manifest storage (built by
collectstatic in prod); tests don't run collectstatic, so we swap in the plain
backend to render templates that {% static %}-reference Unfold's assets.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from predictions import consts
from predictions.models import Prediction

from .factories import join, make_competition, make_league, make_match, make_user


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class UnfoldAdminSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            email="admin-smoke@example.com", password="pw-smoke-12345",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _ok(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, f"{url} -> {resp.status_code}")
        return resp.content.decode()

    def test_index_renders_with_unfold_branding_nav_and_palette(self):
        html = self._ok(reverse("admin:index"))
        # Unfold theme is active (its AdminSite/static is in play).
        self.assertIn("unfold", html)
        # Branding comes from settings.UNFOLD (SITE_HEADER), not admin.site.*.
        self.assertIn(consts.BRAND_NAME, html)
        # Custom grouped sidebar navigation renders (proves UNFOLD["SIDEBAR"]
        # navigation + UnfoldAdminSite.each_context are wired, not just the look).
        self.assertIn(consts.V_COMPETITION_PLURAL, html)
        self.assertIn(consts.ADMIN_NAV_GROUP_PREDICTIONS, html)
        # Brand-red primary palette (UNFOLD["COLORS"]["primary"]["500"]) is applied
        # (Unfold renders the channel triplet as a CSS rgb() function).
        self.assertIn("rgb(239, 62, 66)", html)

    def test_model_changelists_and_forms_render(self):
        # Match changelist: list_editable scores + recompute action + filters.
        self._ok(reverse("admin:predictions_match_changelist"))
        # League add-form: scoring/multiplier fieldsets.
        self._ok(reverse("admin:predictions_league_add"))
        # User add + change forms (Unfold-styled password widgets via our forms).
        self._ok(reverse("admin:accounts_user_add"))
        self._ok(reverse("admin:accounts_user_change", args=[self.admin.pk]))
        # Re-themed auth Group changelist.
        self._ok(reverse("admin:auth_group_changelist"))

    def test_all_sidebar_nav_links_resolve_and_load(self):
        # Every UNFOLD sidebar link must point at a real, loadable admin page.
        from django.conf import settings
        for group in settings.UNFOLD["SIDEBAR"]["navigation"]:
            for item in group["items"]:
                self._ok(str(item["link"]))


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PredictionAdminChangelistTests(TestCase):
    """The prediction changelist must stay fast (no per-row N+1) and offer the
    user/match filters."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            email="pred-admin@example.com", password="pw-12345",
        )
        cls.comp = make_competition()
        cls.league = make_league(cls.comp)
        cls.owner_membership = cls.league.memberships.first()
        cls.url = reverse("admin:predictions_prediction_changelist")

    def setUp(self):
        self.client.force_login(self.admin)

    def _add_predictions(self, n, membership=None):
        membership = membership or self.owner_membership
        for _ in range(n):
            Prediction.objects.create(
                membership=membership, match=make_match(self.comp),
                predicted_home=1, predicted_away=0,
            )

    def _changelist_query_count(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries)

    def test_changelist_has_no_per_row_nplus1(self):
        # list_select_related must keep the query count flat as rows grow.
        self.client.get(self.url)  # warm caches (contenttypes/permissions)
        self._add_predictions(3)
        q_small = self._changelist_query_count()
        self._add_predictions(6)  # 9 rows total
        q_large = self._changelist_query_count()
        self.assertEqual(
            q_small, q_large,
            f"N+1 regression: {q_small} queries for 3 rows but {q_large} for 9",
        )

    def test_filter_by_user(self):
        u2 = make_user()
        mem2 = join(self.league, u2)
        match = make_match(self.comp)
        mine = Prediction.objects.create(
            membership=self.owner_membership, match=match,
            predicted_home=2, predicted_away=2)
        theirs = Prediction.objects.create(
            membership=mem2, match=match, predicted_home=0, predicted_away=1)

        resp = self.client.get(self.url, {"membership__user__id__exact": u2.pk})
        self.assertEqual(resp.status_code, 200)
        rows = list(resp.context["cl"].result_list)
        self.assertEqual(rows, [theirs])
        self.assertNotIn(mine, rows)

    def test_filter_by_match(self):
        target = make_match(self.comp)
        other = make_match(self.comp)
        on_target = Prediction.objects.create(
            membership=self.owner_membership, match=target,
            predicted_home=1, predicted_away=1)
        Prediction.objects.create(
            membership=self.owner_membership, match=other,
            predicted_home=3, predicted_away=0)

        resp = self.client.get(self.url, {"match__id__exact": target.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertCountEqual(resp.context["cl"].result_list, [on_target])
