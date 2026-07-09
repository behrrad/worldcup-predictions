from django.urls import path

from . import api_views

# NOTE: league slugs may contain non-ASCII (Persian) characters, so we use the
# <str:...> converter rather than <slug:...> (which is ASCII-only).
urlpatterns = [
    path("me/", api_views.me, name="api_me"),
    path("me/avatar/", api_views.my_avatar, name="api_my_avatar"),
    # Telegram reminders: link status / connect deep link / notify toggle.
    path("me/telegram/", api_views.me_telegram, name="api_me_telegram"),
    path("teams/", api_views.teams, name="api_teams"),
    path("players/", api_views.players, name="api_players"),
    path("players/<int:user_id>/", api_views.player_detail, name="api_player_detail"),
    # A player's average points-per-prediction over time (across all their leagues).
    path("players/<int:user_id>/average/", api_views.player_average, name="api_player_average"),
    path("competitions/", api_views.competitions, name="api_competitions"),
    # In-play scores (display only; lazily refreshed from the live provider).
    path("live/", api_views.live_scores, name="api_live_scores"),
    # Periodic job trigger (scheduler/cron): reminders + live + finalize.
    # Secret-gated inside the view (X-Task-Key); no Clerk auth.
    path("tasks/tick/", api_views.task_tick, name="api_task_tick"),
    path("leagues/", api_views.leagues, name="api_leagues"),
    path("leagues/join/", api_views.join_league, name="api_join_league"),
    path("leagues/<str:slug>/", api_views.league_detail, name="api_league_detail"),
    path("leagues/<str:slug>/matches/", api_views.league_matches, name="api_league_matches"),
    path("leagues/<str:slug>/matches/<int:match_id>/", api_views.match_detail, name="api_match_detail"),
    path("leagues/<str:slug>/all-predictions/", api_views.league_all_predictions, name="api_league_all_predictions"),
    path("leagues/<str:slug>/members/", api_views.league_members, name="api_league_members"),
    path("leagues/<str:slug>/predictions/", api_views.submit_predictions, name="api_submit_predictions"),
    path("leagues/<str:slug>/leaderboard/", api_views.league_leaderboard, name="api_leaderboard"),
    # Tournament-wide bonus predictions (champion, Golden Boot/Ball, league winner).
    path("leagues/<str:slug>/bonus/", api_views.league_bonus, name="api_league_bonus"),
    path("leagues/<str:slug>/recap/", api_views.league_recap, name="api_league_recap"),
    path("leagues/<str:slug>/fun-stats/", api_views.league_fun_stats, name="api_league_fun_stats"),
    # Points & rank progression per finished match — the player-toggle line chart.
    path("leagues/<str:slug>/progression/", api_views.league_progression, name="api_league_progression"),
    # Public, key-gated results download (no Clerk auth; the key is the credential).
    path("export/<str:key>.xlsx", api_views.export_league, name="api_export_league"),
    # In-app admin: manual result entry (gated to admins inside the views).
    path("admin/matches/", api_views.admin_matches, name="api_admin_matches"),
    path("admin/matches/<int:match_id>/result/", api_views.admin_set_result, name="api_admin_set_result"),
    # In-app admin: enter members' bonus predictions on their behalf.
    path("admin/bonus/leagues/", api_views.admin_bonus_leagues, name="api_admin_bonus_leagues"),
    path("admin/leagues/<str:slug>/bonus/", api_views.admin_league_bonus, name="api_admin_league_bonus"),
]
