from django.contrib import admin

from . import consts, scoring
from .models import (
    Competition,
    League,
    Match,
    MatchScore,
    Membership,
    Prediction,
    Team,
)


class TeamInline(admin.TabularInline):
    model = Team
    extra = 0
    fields = ("group", "name_fa", "name_en", "code", "flag_emoji")


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "is_active", "team_count", "match_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TeamInline]

    @admin.display(description=consts.V_TEAM_PLURAL)
    def team_count(self, obj):
        return obj.teams.count()

    @admin.display(description=consts.V_MATCH_PLURAL)
    def match_count(self, obj):
        return obj.matches.count()


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name_fa", "name_en", "code", "group", "competition")
    list_filter = ("competition", "group")
    search_fields = ("name_fa", "name_en", "code")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "match_label", "stage", "kickoff", "home_score", "away_score", "status",
    )
    list_display_links = ("match_label",)
    list_editable = ("home_score", "away_score")  # enter results right in the list
    list_filter = ("competition", "stage", "status")
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
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "competition", "owner", "invite_code",
                    "member_count", "is_active", "created_at")
    list_filter = ("competition", "is_active")
    search_fields = ("name", "invite_code", "owner__email")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    autocomplete_fields = ("owner",)
    actions = ["recompute_league_scores_action"]

    fieldsets = (
        (consts.ADMIN_SECTION_GENERAL, {
            "fields": ("name", "slug", "competition", "owner", "description",
                       "invite_code", "is_active", "created_at"),
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
    )

    @admin.display(description=consts.COL_MEMBER_COUNT)
    def member_count(self, obj):
        return obj.memberships.count()

    @admin.action(description=consts.ACTION_RECOMPUTE_LEAGUE)
    def recompute_league_scores_action(self, request, queryset):
        total = sum(scoring.recompute_league_scores(league) for league in queryset)
        self.message_user(request, consts.MSG_ADMIN_RECOMPUTED.format(n=total))


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "league", "role", "joined_at")
    list_filter = ("league", "role")
    search_fields = ("user__email", "user__display_name", "league__name")
    autocomplete_fields = ("user", "league")


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ("membership", "match", "predicted_home", "predicted_away", "updated_at")
    list_filter = ("match__competition", "match__stage")
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership", "match")


@admin.register(MatchScore)
class MatchScoreAdmin(admin.ModelAdmin):
    list_display = ("membership", "match", "points", "tier", "computed_at")
    list_filter = ("tier", "match__competition", "match__stage")
    search_fields = ("membership__user__email", "membership__user__display_name")
    autocomplete_fields = ("membership", "match")
    readonly_fields = ("computed_at",)
