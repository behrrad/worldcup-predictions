from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import AutocompleteSelectFilter

from . import consts, scoring
from .models import (
    BonusPrediction,
    BonusScore,
    Competition,
    League,
    Match,
    MatchScore,
    Membership,
    PlayerCandidate,
    Prediction,
    Team,
    TournamentOutcome,
    generate_export_key,
)


class TeamInline(TabularInline):
    model = Team
    extra = 0
    fields = ("group", "name_fa", "name_en", "code", "flag_emoji")


class PlayerCandidateInline(TabularInline):
    model = PlayerCandidate
    extra = 0
    fields = ("name", "team")
    autocomplete_fields = ("team",)


@admin.register(Competition)
class CompetitionAdmin(ModelAdmin):
    list_display = ("name", "start_date", "is_active", "team_count", "match_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TeamInline, PlayerCandidateInline]

    @admin.display(description=consts.V_TEAM_PLURAL)
    def team_count(self, obj):
        return obj.teams.count()

    @admin.display(description=consts.V_MATCH_PLURAL)
    def match_count(self, obj):
        return obj.matches.count()


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ("name_fa", "name_en", "code", "group", "competition")
    list_filter = ("competition", "group")
    search_fields = ("name_fa", "name_en", "code")


@admin.register(Match)
class MatchAdmin(ModelAdmin):
    list_display = (
        "match_label", "stage", "kickoff", "home_score", "away_score", "status",
        "count_for_scoring",
    )
    list_display_links = ("match_label",)
    # Enter results / void a match from scoring right in the list.
    list_editable = ("home_score", "away_score", "count_for_scoring")
    list_filter = ("competition", "stage", "status", "count_for_scoring")
    search_fields = ("home_team__name_fa", "away_team__name_fa")
    autocomplete_fields = ("home_team", "away_team")
    date_hierarchy = "kickoff"
    ordering = ("kickoff", "match_number")
    actions = ["recompute_scores"]

    @admin.display(description=consts.V_MATCH)
    def match_label(self, obj):
        return str(obj)

    @admin.action(description=consts.ACTION_RECOMPUTE_MATCH)
    def recompute_scores(self, request, queryset):
        total = sum(scoring.recompute_match_scores(m) for m in queryset)
        self.message_user(request, consts.MSG_ADMIN_RECOMPUTED.format(n=total))


@admin.register(League)
class LeagueAdmin(ModelAdmin):
    list_display = ("name", "competition", "owner", "invite_code",
                    "member_count", "is_active", "created_at")
    list_filter = ("competition", "is_active")
    search_fields = ("name", "invite_code", "export_key", "owner__email")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "export_key")
    autocomplete_fields = ("owner",)
    actions = ["recompute_league_scores_action", "regenerate_export_key_action"]

    fieldsets = (
        (consts.ADMIN_SECTION_GENERAL, {
            "fields": ("name", "slug", "competition", "owner", "description",
                       "invite_code", "export_key", "is_active", "created_at"),
        }),
        (consts.ADMIN_SECTION_SCORING, {
            "fields": ("lock_minutes", "reveal_predictions", "points_exact",
                       "points_correct_diff", "points_correct_winner",
                       "points_participation"),
        }),
        (consts.ADMIN_SECTION_MULTIPLIERS, {
            "fields": ("multiplier_group", "multiplier_r32", "multiplier_r16",
                       "multiplier_qf", "multiplier_sf", "multiplier_tp",
                       "multiplier_final"),
        }),
        (consts.ADMIN_SECTION_BONUS, {
            "fields": ("bonus_lock_at", "points_champion", "points_runner_up",
                       "points_third", "points_fourth", "points_golden_boot",
                       "points_golden_ball", "points_league_winner"),
        }),
    )

    @admin.display(description=consts.COL_MEMBER_COUNT)
    def member_count(self, obj):
        return obj.memberships.count()

    @admin.action(description=consts.ACTION_RECOMPUTE_LEAGUE)
    def recompute_league_scores_action(self, request, queryset):
        total = sum(scoring.recompute_league_scores(league) for league in queryset)
        self.message_user(request, consts.MSG_ADMIN_RECOMPUTED.format(n=total))

    @admin.action(description=consts.ACTION_REGENERATE_EXPORT_KEY)
    def regenerate_export_key_action(self, request, queryset):
        n = 0
        for league in queryset:
            league.export_key = generate_export_key()
            league.save(update_fields=["export_key"])
            n += 1
        self.message_user(request, consts.MSG_ADMIN_EXPORT_KEYS_REGENERATED.format(n=n))


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = ("user", "league", "role", "joined_at")
    list_filter = ("league", "role")
    search_fields = ("user__email", "user__display_name", "league__name")
    autocomplete_fields = ("user", "league")


@admin.register(Prediction)
class PredictionAdmin(ModelAdmin):
    list_display = ("membership", "match", "predicted_home", "predicted_away", "updated_at")
    # Each row renders membership.__str__ (user + league) and match.__str__ (both
    # teams). Without this, that's ~6 lazy queries per row (an N+1 that made the
    # changelist slow); pull them all in one JOIN.
    list_select_related = (
        "membership__user", "membership__league",
        "match__home_team", "match__away_team",
    )
    list_filter = (
        "membership__user",                     # filter by user
        ("match", AutocompleteSelectFilter),    # filter by a specific match (searchable)
        "match__competition",
        "match__stage",
    )
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership", "match")
    # The predictions table is the largest; skip the extra unfiltered COUNT(*).
    show_full_result_count = False


@admin.register(MatchScore)
class MatchScoreAdmin(ModelAdmin):
    list_display = ("membership", "match", "points", "tier", "computed_at")
    list_filter = ("tier", "match__competition", "match__stage")
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership", "match")
    readonly_fields = ("computed_at",)


# --------------------------------------------------------------------------- #
# Tournament-wide bonus predictions
# --------------------------------------------------------------------------- #
def _autofill_places(outcome) -> int:
    """Fill champion/runner-up (from the final) and 3rd/4th (from the third-place
    match) from the recorded results. Skips a match with no clear winner (a draw
    decided on penalties, which the score fields don't capture). Returns how many
    placements were set."""
    comp = outcome.competition
    n = 0
    final = comp.matches.filter(stage=consts.Stage.FINAL).order_by("kickoff").first()
    if (final and final.is_finished and final.home_team_id and final.away_team_id
            and final.home_score != final.away_score):
        if final.home_score > final.away_score:
            outcome.champion, outcome.runner_up = final.home_team, final.away_team
        else:
            outcome.champion, outcome.runner_up = final.away_team, final.home_team
        n += 2
    tp = comp.matches.filter(stage=consts.Stage.THIRD_PLACE).order_by("kickoff").first()
    if (tp and tp.is_finished and tp.home_team_id and tp.away_team_id
            and tp.home_score != tp.away_score):
        if tp.home_score > tp.away_score:
            outcome.third_place, outcome.fourth_place = tp.home_team, tp.away_team
        else:
            outcome.third_place, outcome.fourth_place = tp.away_team, tp.home_team
        n += 2
    outcome.save()
    return n


@admin.register(PlayerCandidate)
class PlayerCandidateAdmin(ModelAdmin):
    list_display = ("name", "team", "competition")
    list_filter = ("competition",)
    search_fields = ("name",)
    autocomplete_fields = ("competition", "team")


@admin.register(TournamentOutcome)
class TournamentOutcomeAdmin(ModelAdmin):
    list_display = ("competition", "champion", "runner_up", "third_place",
                    "fourth_place", "golden_boot", "golden_ball", "settled_at")
    autocomplete_fields = ("competition", "champion", "runner_up", "third_place",
                           "fourth_place", "golden_boot", "golden_ball")
    readonly_fields = ("settled_at",)
    actions = ["autofill_places_action", "settle_bonus_action"]

    @admin.action(description=consts.ACTION_AUTOFILL_PLACES)
    def autofill_places_action(self, request, queryset):
        total = sum(_autofill_places(o) for o in queryset)
        self.message_user(request, consts.MSG_ADMIN_PLACES_AUTOFILLED.format(n=total))

    @admin.action(description=consts.ACTION_SETTLE_BONUS)
    def settle_bonus_action(self, request, queryset):
        now = timezone.now()
        total = 0
        for outcome in queryset:
            total += scoring.settle_bonus_scores(outcome.competition)
            outcome.settled_at = now
            outcome.save(update_fields=["settled_at"])
        self.message_user(request, consts.MSG_ADMIN_BONUS_SETTLED.format(n=total))


@admin.register(BonusPrediction)
class BonusPredictionAdmin(ModelAdmin):
    list_display = ("membership", "kind", "team", "player", "target_membership",
                    "updated_at")
    list_filter = ("kind", "membership__league")
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership", "team", "player", "target_membership")


@admin.register(BonusScore)
class BonusScoreAdmin(ModelAdmin):
    list_display = ("membership", "kind", "points", "correct", "computed_at")
    list_filter = ("kind", "correct", "membership__league")
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership",)
    readonly_fields = ("computed_at",)
