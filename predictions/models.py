import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from . import consts


def generate_invite_code() -> str:
    """Return a short, human-friendly invite code."""
    return "".join(
        secrets.choice(consts.INVITE_CODE_ALPHABET)
        for _ in range(consts.INVITE_CODE_LENGTH)
    )


def generate_export_key() -> str:
    """Return a URL-safe token used to download a league's results spreadsheet."""
    return secrets.token_urlsafe(consts.EXPORT_KEY_BYTES)


def fa_to_latin_slug(text: str) -> str:
    """Transliterate Persian text to a readable ASCII slug.

    League/competition names are Persian; slugify(..., allow_unicode=True) would
    keep them Persian and percent-encode into gibberish in URLs. We map each
    Persian letter to its Latin equivalent (consts.FA_TO_LATIN) first, then run
    the ASCII slugify, so «لیگ دوستان» becomes "lig-dustan". Any character not in
    the map (Latin letters, digits, spaces, punctuation) passes through to
    slugify untouched, so English names keep working as before.
    """
    transliterated = "".join(consts.FA_TO_LATIN.get(ch, ch) for ch in text)
    return slugify(transliterated)  # ASCII slugify: lowercases, strips, hyphenates


# --------------------------------------------------------------------------- #
# The real-world football event (e.g. World Cup 2026)
# --------------------------------------------------------------------------- #
class Competition(models.Model):
    name = models.CharField(consts.L_NAME, max_length=120)
    slug = models.SlugField(consts.L_SLUG, max_length=140, unique=True, blank=True,
                            allow_unicode=True)
    start_date = models.DateField(consts.L_START_DATE, null=True, blank=True)
    is_active = models.BooleanField(consts.L_IS_ACTIVE, default=True)

    class Meta:
        verbose_name = consts.V_COMPETITION
        verbose_name_plural = consts.V_COMPETITION_PLURAL
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = fa_to_latin_slug(self.name) or consts.SLUG_FALLBACK_COMPETITION
        super().save(*args, **kwargs)


class Team(models.Model):
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="teams",
        verbose_name=consts.L_COMPETITION,
    )
    name_fa = models.CharField(consts.L_TEAM_NAME_FA, max_length=80)
    name_en = models.CharField(consts.L_TEAM_NAME_EN, max_length=80, blank=True)
    code = models.CharField(consts.L_TEAM_CODE, max_length=3, blank=True)
    flag_emoji = models.CharField(consts.L_TEAM_FLAG, max_length=8, blank=True)
    group = models.CharField(consts.L_TEAM_GROUP, max_length=2, blank=True)

    class Meta:
        verbose_name = consts.V_TEAM
        verbose_name_plural = consts.V_TEAM_PLURAL
        ordering = ["group", "name_fa"]
        constraints = [
            models.UniqueConstraint(
                fields=["competition", "name_fa"], name="unique_team_per_competition"
            ),
        ]

    def __str__(self):
        flag = f"{self.flag_emoji} " if self.flag_emoji else ""
        return f"{flag}{self.name_fa}"


# --------------------------------------------------------------------------- #
# A single match in the competition (the real result is entered once)
# --------------------------------------------------------------------------- #
class Match(models.Model):
    competition = models.ForeignKey(
        Competition, on_delete=models.CASCADE, related_name="matches",
        verbose_name=consts.L_COMPETITION,
    )
    match_number = models.PositiveIntegerField(consts.L_MATCH_NUMBER, null=True, blank=True)
    stage = models.CharField(
        consts.L_STAGE, max_length=8,
        choices=consts.STAGE_CHOICES, default=consts.Stage.GROUP,
    )
    home_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="home_matches", verbose_name=consts.L_HOME_TEAM,
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="away_matches", verbose_name=consts.L_AWAY_TEAM,
    )
    kickoff = models.DateTimeField(consts.L_KICKOFF)
    home_score = models.PositiveSmallIntegerField(consts.L_HOME_SCORE, null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(consts.L_AWAY_SCORE, null=True, blank=True)
    status = models.CharField(
        consts.L_STATUS, max_length=12,
        choices=consts.MATCH_STATUS_CHOICES, default=consts.MatchStatus.SCHEDULED,
    )
    venue = models.CharField(consts.L_VENUE, max_length=120, blank=True)
    # Bracket-slot placeholders for knockout matches whose teams aren't known yet
    # (e.g. "Group A Winner", "Match 73 Winner"). Stored as the source English
    # labels; translated to Persian for display in the API layer.
    home_label = models.CharField(consts.L_HOME_LABEL, max_length=60, blank=True)
    away_label = models.CharField(consts.L_AWAY_LABEL, max_length=60, blank=True)

    class Meta:
        verbose_name = consts.V_MATCH
        verbose_name_plural = consts.V_MATCH_PLURAL
        ordering = ["kickoff", "match_number"]

    def __str__(self):
        home = self.home_team.name_fa if self.home_team else "نامشخص"
        away = self.away_team.name_fa if self.away_team else "نامشخص"
        return f"{home} - {away}"

    def save(self, *args, **kwargs):
        # Entering both scores marks the match finished; clearing them reverts it.
        self.status = (
            consts.MatchStatus.FINISHED if self.has_result
            else consts.MatchStatus.SCHEDULED
        )
        super().save(*args, **kwargs)

    # -- result helpers ---------------------------------------------------- #
    @property
    def has_result(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    @property
    def is_finished(self) -> bool:
        """A match is scored once both final scores are entered."""
        return self.has_result

    # -- lock helpers ------------------------------------------------------ #
    def lock_time(self, lock_minutes: int):
        """The moment predictions close for this match in a given league."""
        return self.kickoff - timedelta(minutes=lock_minutes)

    def is_open_for(self, lock_minutes: int, now=None) -> bool:
        """Can a prediction still be submitted/edited?"""
        now = now or timezone.now()
        return not self.is_finished and now < self.lock_time(lock_minutes)


# --------------------------------------------------------------------------- #
# A friends' prediction league (the "tournament" the user runs)
# --------------------------------------------------------------------------- #
class League(models.Model):
    name = models.CharField(consts.L_NAME, max_length=120)
    slug = models.SlugField(consts.L_SLUG, max_length=140, unique=True, blank=True,
                            allow_unicode=True, help_text=consts.HELP_SLUG)
    competition = models.ForeignKey(
        Competition, on_delete=models.PROTECT, related_name="leagues",
        verbose_name=consts.L_COMPETITION,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="owned_leagues", verbose_name=consts.L_OWNER,
    )
    description = models.TextField(consts.L_DESCRIPTION, blank=True)
    invite_code = models.CharField(
        consts.L_INVITE_CODE, max_length=16, unique=True,
        default=generate_invite_code, help_text=consts.HELP_INVITE_CODE,
    )
    # Anyone holding this key can download the league's results .xlsx (a separate
    # secret from the invite code, so sharing the export never lets someone join).
    export_key = models.CharField(
        consts.L_EXPORT_KEY, max_length=consts.EXPORT_KEY_MAX_LENGTH, unique=True,
        default=generate_export_key, help_text=consts.HELP_EXPORT_KEY,
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Membership", related_name="leagues",
    )

    # Scoring configuration (editable per league) -------------------------- #
    lock_minutes = models.PositiveIntegerField(
        consts.L_LOCK_MINUTES, default=consts.DEFAULT_LOCK_MINUTES,
        help_text=consts.HELP_LOCK_MINUTES,
    )
    # When False, other members' predictions stay hidden even after a match
    # locks. The owner toggles this from the league page.
    reveal_predictions = models.BooleanField(
        consts.L_REVEAL_PREDICTIONS, default=consts.DEFAULT_REVEAL_PREDICTIONS,
        help_text=consts.HELP_REVEAL_PREDICTIONS,
    )
    points_exact = models.IntegerField(consts.L_POINTS_EXACT, default=consts.DEFAULT_POINTS_EXACT)
    points_correct_diff = models.IntegerField(
        consts.L_POINTS_CORRECT_DIFF, default=consts.DEFAULT_POINTS_CORRECT_DIFF)
    points_correct_winner = models.IntegerField(
        consts.L_POINTS_CORRECT_WINNER, default=consts.DEFAULT_POINTS_CORRECT_WINNER)
    points_participation = models.IntegerField(
        consts.L_POINTS_PARTICIPATION, default=consts.DEFAULT_POINTS_PARTICIPATION)

    # Per-stage multipliers ------------------------------------------------ #
    multiplier_group = models.DecimalField(
        consts.L_MULT_GROUP, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_GROUP_MULTIPLIER)
    multiplier_r32 = models.DecimalField(
        consts.L_MULT_R32, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)
    multiplier_r16 = models.DecimalField(
        consts.L_MULT_R16, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)
    multiplier_qf = models.DecimalField(
        consts.L_MULT_QF, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)
    multiplier_sf = models.DecimalField(
        consts.L_MULT_SF, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)
    multiplier_tp = models.DecimalField(
        consts.L_MULT_TP, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)
    multiplier_final = models.DecimalField(
        consts.L_MULT_FINAL, max_digits=4, decimal_places=2,
        default=consts.DEFAULT_KNOCKOUT_MULTIPLIER)

    is_active = models.BooleanField(consts.L_IS_ACTIVE, default=True)
    created_at = models.DateTimeField(consts.L_CREATED_AT, auto_now_add=True)

    class Meta:
        verbose_name = consts.V_LEAGUE
        verbose_name_plural = consts.V_LEAGUE_PLURAL
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # Slugs are unique; two leagues sharing a name (e.g. "Friends") would
            # otherwise collide and raise IntegrityError on create. Append a
            # numeric suffix until the slug is free.
            base = fa_to_latin_slug(self.name) or consts.SLUG_FALLBACK_LEAGUE
            slug = base
            n = 2
            while League.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        # The user-facing league page is rendered by the Next.js frontend, not
        # Django, so point at FRONTEND_URL/l/<slug> (used by admin "View on site").
        return f"{settings.FRONTEND_URL}{consts.LEAGUE_DETAIL_PATH.format(slug=self.slug)}"

    def export_path(self) -> str:
        """Relative API path of this league's key-gated results download."""
        return consts.EXPORT_PATH_TEMPLATE.format(key=self.export_key)

    # Map each stage to its configured multiplier field.
    @property
    def _stage_multiplier_map(self):
        return {
            consts.Stage.GROUP: self.multiplier_group,
            consts.Stage.ROUND_OF_32: self.multiplier_r32,
            consts.Stage.ROUND_OF_16: self.multiplier_r16,
            consts.Stage.QUARTER: self.multiplier_qf,
            consts.Stage.SEMI: self.multiplier_sf,
            consts.Stage.THIRD_PLACE: self.multiplier_tp,
            consts.Stage.FINAL: self.multiplier_final,
        }

    def multiplier_for(self, stage: str):
        return self._stage_multiplier_map.get(stage, consts.DEFAULT_GROUP_MULTIPLIER)


class Membership(models.Model):
    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="memberships",
        verbose_name=consts.L_LEAGUE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="memberships", verbose_name=consts.L_USER,
    )
    role = models.CharField(
        consts.L_ROLE, max_length=8,
        choices=consts.ROLE_CHOICES, default=consts.Role.MEMBER,
    )
    joined_at = models.DateTimeField(consts.L_JOINED_AT, auto_now_add=True)

    class Meta:
        verbose_name = consts.V_MEMBERSHIP
        verbose_name_plural = consts.V_MEMBERSHIP_PLURAL
        ordering = ["joined_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "user"], name="unique_member_per_league"
            ),
        ]

    def __str__(self):
        return f"{self.user.public_name} @ {self.league.name}"

    @property
    def is_owner(self) -> bool:
        return self.role == consts.Role.OWNER


class Prediction(models.Model):
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="predictions",
        verbose_name=consts.L_MEMBERSHIP,
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="predictions",
        verbose_name=consts.L_MATCH,
    )
    predicted_home = models.PositiveSmallIntegerField(consts.L_PREDICTED_HOME)
    predicted_away = models.PositiveSmallIntegerField(consts.L_PREDICTED_AWAY)
    created_at = models.DateTimeField(consts.L_CREATED_AT, auto_now_add=True)
    updated_at = models.DateTimeField(consts.L_UPDATED_AT, auto_now=True)

    class Meta:
        verbose_name = consts.V_PREDICTION
        verbose_name_plural = consts.V_PREDICTION_PLURAL
        ordering = ["match__kickoff"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "match"], name="unique_prediction_per_match"
            ),
        ]

    def __str__(self):
        return f"{self.membership.user.public_name}: {self.predicted_home}-{self.predicted_away}"


class MatchScore(models.Model):
    """The points a member earned on a single match (recomputed on result entry)."""

    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="scores",
        verbose_name=consts.L_MEMBERSHIP,
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="scores",
        verbose_name=consts.L_MATCH,
    )
    points = models.DecimalField(consts.L_POINTS, max_digits=6, decimal_places=2, default=0)
    tier = models.CharField(
        consts.L_TIER, max_length=16,
        choices=consts.TIER_CHOICES, default=consts.Tier.NONE,
    )
    computed_at = models.DateTimeField(consts.L_COMPUTED_AT, auto_now=True)

    class Meta:
        verbose_name = consts.V_MATCHSCORE
        verbose_name_plural = consts.V_MATCHSCORE_PLURAL
        ordering = ["-match__kickoff"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "match"], name="unique_score_per_match"
            ),
        ]

    def __str__(self):
        return f"{self.membership.user.public_name}: {self.points}"
