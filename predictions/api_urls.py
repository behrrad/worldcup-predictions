from django.urls import path

from . import api_views

# NOTE: league slugs may contain non-ASCII (Persian) characters, so we use the
# <str:...> converter rather than <slug:...> (which is ASCII-only).
urlpatterns = [
    path("me/", api_views.me, name="api_me"),
    path("me/avatar/", api_views.my_avatar, name="api_my_avatar"),
    path("teams/", api_views.teams, name="api_teams"),
    path("players/", api_views.players, name="api_players"),
    path("players/<int:user_id>/", api_views.player_detail, name="api_player_detail"),
    path("competitions/", api_views.competitions, name="api_competitions"),
    path("leagues/", api_views.leagues, name="api_leagues"),
    path("leagues/join/", api_views.join_league, name="api_join_league"),
    path("leagues/<str:slug>/", api_views.league_detail, name="api_league_detail"),
    path("leagues/<str:slug>/matches/", api_views.league_matches, name="api_league_matches"),
    path("leagues/<str:slug>/matches/<int:match_id>/", api_views.match_detail, name="api_match_detail"),
    path("leagues/<str:slug>/members/", api_views.league_members, name="api_league_members"),
    path("leagues/<str:slug>/predictions/", api_views.submit_predictions, name="api_submit_predictions"),
    path("leagues/<str:slug>/leaderboard/", api_views.league_leaderboard, name="api_leaderboard"),
]
