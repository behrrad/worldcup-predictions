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
from django.test import TestCase, override_settings
from django.urls import reverse

from predictions import consts


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
