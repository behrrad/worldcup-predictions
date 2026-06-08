from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from predictions import consts
from predictions.models import fa_to_latin_slug, generate_invite_code

from .factories import make_competition, make_league, make_match


class InviteCodeTests(TestCase):
    def test_length_and_alphabet(self):
        code = generate_invite_code()
        self.assertEqual(len(code), consts.INVITE_CODE_LENGTH)
        self.assertTrue(all(c in consts.INVITE_CODE_ALPHABET for c in code))

    def test_codes_are_unique_per_league(self):
        comp = make_competition()
        a = make_league(comp, name="A")
        b = make_league(comp, name="B")
        self.assertNotEqual(a.invite_code, b.invite_code)


class TransliterationTests(TestCase):
    """fa_to_latin_slug turns Persian names into readable ASCII slugs."""

    def test_known_examples(self):
        # Lock the mapping for representative names (approximate, by design).
        cases = {
            "لیگ دوستان": "lig-dustan",
            "لیگ دموی نمایش": "lig-dmui-nmaish",
            "رفقای فوتبال": "rfghai-futbal",
            # «ى» (alef maksura) is the long-ā ending of these names, so -> "a".
            "موسى": "musa",
            "مصطفى": "mstfa",
            # «ۀ» (heh with yeh / ezafe) -> "e".
            "خانۀ ما": "khane-ma",
        }
        for name, expected in cases.items():
            self.assertEqual(fa_to_latin_slug(name), expected, name)

    def test_zero_width_non_joiner_is_dropped(self):
        # «پیش‌بینی» contains a ZWNJ between پیش and بینی; it must not survive.
        self.assertEqual(fa_to_latin_slug("پیش‌بینی"), "pishbini")

    def test_persian_digits_become_ascii(self):
        self.assertEqual(fa_to_latin_slug("جام ۲۰۲۶"), "jam-2026")

    def test_ascii_names_pass_through(self):
        self.assertEqual(fa_to_latin_slug("Friends League"), "friends-league")

    def test_result_is_always_ascii(self):
        slug = fa_to_latin_slug("لیگ خانوادگی ⚽")
        self.assertTrue(slug.isascii())
        self.assertNotIn(" ", slug)

    def test_unmappable_name_is_empty(self):
        # Only emoji/punctuation -> empty; callers fall back to a default.
        self.assertEqual(fa_to_latin_slug("⚽🏆"), "")


class SlugTests(TestCase):
    def test_persian_name_gets_readable_ascii_slug(self):
        comp = make_competition(name="جام جهانی")
        league = make_league(comp, name="رفقای فوتبال")
        self.assertEqual(league.slug, "rfghai-futbal")
        self.assertTrue(league.slug.isascii())  # no percent-encoded URLs

    def test_emoji_only_name_falls_back(self):
        league = make_league(make_competition(), name="🏆⚽")
        self.assertEqual(league.slug, consts.SLUG_FALLBACK_LEAGUE)

    def test_duplicate_names_get_unique_slugs(self):
        # Two leagues with the same name must not collide on the unique slug.
        comp = make_competition()
        a = make_league(comp, name="Friends")
        b = make_league(comp, name="Friends")
        self.assertNotEqual(a.slug, b.slug)
        self.assertEqual(a.slug, "friends")
        self.assertEqual(b.slug, "friends-2")


class AbsoluteUrlTests(TestCase):
    def test_points_at_frontend_league_page(self):
        # Must not raise (it used to reverse a non-existent "league_detail")
        # and must point at the real Next.js page at FRONTEND_URL/l/<slug>.
        league = make_league(make_competition(), name="رفقای فوتبال")
        url = league.get_absolute_url()
        self.assertEqual(url, f"{settings.FRONTEND_URL}/l/{league.slug}")
        self.assertTrue(url.startswith(settings.FRONTEND_URL))


class MultiplierTests(TestCase):
    def test_defaults(self):
        league = make_league(make_competition())
        self.assertEqual(league.multiplier_for(consts.Stage.GROUP), Decimal("1.0"))
        self.assertEqual(league.multiplier_for(consts.Stage.FINAL), Decimal("1.5"))
        self.assertEqual(league.multiplier_for(consts.Stage.QUARTER), Decimal("1.5"))

    def test_unknown_stage_defaults_to_group(self):
        league = make_league(make_competition())
        self.assertEqual(league.multiplier_for("UNKNOWN"), consts.DEFAULT_GROUP_MULTIPLIER)


class MatchStatusTests(TestCase):
    def test_entering_scores_marks_finished(self):
        m = make_match(make_competition())
        self.assertFalse(m.is_finished)
        self.assertEqual(m.status, consts.MatchStatus.SCHEDULED)
        m.home_score, m.away_score = 1, 0
        m.save()
        self.assertTrue(m.is_finished)
        self.assertEqual(m.status, consts.MatchStatus.FINISHED)

    def test_partial_score_is_not_finished(self):
        m = make_match(make_competition())
        m.home_score = 1  # only one side
        m.save()
        self.assertFalse(m.has_result)
        self.assertFalse(m.is_finished)


class LockWindowTests(TestCase):
    def setUp(self):
        self.comp = make_competition()
        self.now = timezone.now()

    def test_open_well_before_kickoff(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        self.assertTrue(m.is_open_for(30, now=self.now))

    def test_closed_inside_lock_window(self):
        # kickoff in 10 min, lock is 30 min before -> already closed
        m = make_match(self.comp, kickoff=self.now + timedelta(minutes=10))
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_closed_after_kickoff(self):
        m = make_match(self.comp, kickoff=self.now - timedelta(minutes=5))
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_finished_match_is_closed(self):
        m = make_match(self.comp, kickoff=self.now + timedelta(hours=2))
        m.home_score, m.away_score = 1, 1
        m.save()
        self.assertFalse(m.is_open_for(30, now=self.now))

    def test_lock_time_calculation(self):
        kickoff = self.now + timedelta(hours=1)
        m = make_match(self.comp, kickoff=kickoff)
        self.assertEqual(m.lock_time(30), kickoff - timedelta(minutes=30))
