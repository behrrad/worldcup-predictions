export interface TeamT {
  id: number;
  name: string;
  name_en: string;
  code: string;
  flag: string;
  group: string;
}

export interface MeT {
  email: string;
  display_name: string;
  public_name: string;
  is_admin: boolean;
}

export interface AdminMatchT {
  id: number;
  match_number: number | null;
  stage: string;
  stage_label: string;
  kickoff: string;
  venue: string | null;
  competition: { name: string; slug: string };
  home_team: TeamT | null;
  away_team: TeamT | null;
  home_label: string | null;
  away_label: string | null;
  home_score: number | null;
  away_score: number | null;
  // Knockout shootout winner (HOME/AWAY) when a match was level at 120'; null otherwise.
  penalty_winner: string | null;
  is_finished: boolean;
  status: string;
}

// In-play state of a match (display only — points always come from the
// official result). status: "LIVE" | "HT" | "FT"; minute uses Latin digits
// like "45+4" — render with fa().
export interface LiveInfoT {
  status: string;
  status_label: string | null;
  minute: string | null;
  home: number | null;
  away: number | null;
}

// One currently-live match on the /live/ ticker payload.
export interface LiveMatchT extends LiveInfoT {
  id: number;
  kickoff: string;
  home_team: TeamT | null;
  away_team: TeamT | null;
}

export interface LiveScoresResp {
  checked_at: string;
  matches: LiveMatchT[];
}

export interface MatchT {
  id: number;
  stage: string;
  stage_label: string;
  kickoff: string;
  venue: string | null;
  home_team: TeamT | null;
  away_team: TeamT | null;
  home_label: string | null;
  away_label: string | null;
  home_score: number | null;
  away_score: number | null;
  // Knockout shootout winner (HOME/AWAY) when a match was level at 120'; null
  // otherwise. home_score/away_score stay the 120' draw.
  penalty_winner: string | null;
  // Live (in-play) state, or null when the match isn't being played right now.
  live: LiveInfoT | null;
  is_finished: boolean;
  // When false the match is voided: it earns no points and is left out of the
  // standings, though the prediction and result are still shown.
  counts_for_scoring: boolean;
  is_open: boolean;
  can_predict: boolean;
  lock_time: string;
  // `advancer` (HOME/AWAY) is the side picked to go through on penalties — only
  // set on a knockout draw prediction; null otherwise.
  my_prediction: { home: number; away: number; advancer: string | null } | null;
  my_points: number | null;
  tier: string | null;
  tier_label: string | null;
}

export interface LeagueCard {
  slug: string;
  name: string;
  competition: string;
  role: string;
  is_owner: boolean;
  member_count: number;
}

export interface StageMult {
  stage: string;
  label: string;
  multiplier: number;
}

export interface LeagueDetail {
  slug: string;
  name: string;
  description: string;
  competition: { name: string; slug: string };
  member_count: number;
  is_owner: boolean;
  role: string;
  invite_code: string | null;
  // When false, other members' predictions stay hidden even after a match locks.
  // Toggled by the owner; see RevealToggle.
  reveal_predictions: boolean;
  // Shared with the whole league: anyone can use this link to download the
  // results .xlsx (upcoming predictions stay hidden inside the file).
  export_key: string;
  export_url: string;
  scoring: {
    points_exact: number;
    points_correct_diff: number;
    points_correct_winner: number;
    points_participation: number;
    lock_minutes: number;
    stage_multipliers: StageMult[];
    // Tournament-wide bonus questions (enabled per league via bonus_lock_at).
    bonus_enabled: boolean;
    bonus_lock_at: string | null;
    points_champion: number;
    points_runner_up: number;
    points_third: number;
    points_fourth: number;
    points_golden_boot: number;
    points_golden_ball: number;
    points_league_winner: number;
  };
}

// One member's predicted score for a single live match (null when they didn't predict).
export interface LivePickT {
  match_id: number;
  home: number | null;
  away: number | null;
}

// Compact live-match descriptor used in the leaderboard's picks column.
export interface LiveMatchInfo {
  id: number;
  home_team: TeamT | null;
  away_team: TeamT | null;
  live_home: number;
  live_away: number;
}

export interface LeaderRow {
  rank: number;
  name: string;
  total: number;
  // Split of the total: per-match points vs. settled tournament-bonus points
  // (bonus_total is 0 until the bonus is settled at tournament end).
  match_total: number;
  bonus_total: number;
  played: number;
  exact_count: number;
  is_me: boolean;
  // Live view: official total plus provisional points from in-play matches
  // (the current live score played as the final result). When nothing is
  // live these mirror the official fields.
  live_rank: number;
  live_total: number;
  live_points: number;
  // Per-live-match picks for this member (aligned with LeaderboardResp.live_matches).
  live_picks: LivePickT[];
  // Points-per-game view: average points per predicted game (4 decimals),
  // the member's rank among those eligible (null if not), and whether they
  // predicted at least half of the finished matches so far.
  avg_points: number;
  avg_rank: number | null;
  eligible_for_avg: boolean;
}

export interface LeaderboardResp {
  // True while at least one match is in play — the live view then differs
  // from the official one and the UI shows both tabs.
  is_live: boolean;
  // In-play matches — empty when is_live is false.
  live_matches: LiveMatchInfo[];
  rows: LeaderRow[];
}

export interface CompetitionT {
  id: number;
  name: string;
  slug: string;
}

export interface MatchDetailResp {
  match: MatchT;
  revealed: boolean;
  // The league's owner-controlled setting. When false, picks never reveal (so a
  // hidden table means "owner turned it off", not just "not locked yet").
  reveal_predictions: boolean;
  lock_time: string;
  member_count: number;
  // Before lock: `name`/`is_me` are set but `home`/`away`/`points` are null
  // (we show who predicted, not what). After lock everything is filled in.
  predictions: {
    name: string;
    home: number | null;
    away: number | null;
    // The side this member picked to advance on penalties (HOME/AWAY), revealed
    // with their score; null otherwise.
    advancer: string | null;
    points: number | null;
    tier_label: string | null;
    is_me: boolean;
  }[];
}

// One member's prediction on a match, as shown on the "Everyone's predictions"
// board. Before a match reveals, `home`/`away`/`points` are null (we only show
// that the person predicted, not what).
export interface AllPredEntry {
  name: string;
  avatar: string | null;
  is_me: boolean;
  home: number | null;
  away: number | null;
  // Picked side to advance on penalties (HOME/AWAY), revealed with the score.
  advancer: string | null;
  points: number | null;
  tier: string | null;
  tier_label: string | null;
}

export interface AllPredMatch {
  id: number;
  stage: string;
  stage_label: string;
  kickoff: string;
  home_team: TeamT | null;
  away_team: TeamT | null;
  home_label: string | null;
  away_label: string | null;
  home_score: number | null;
  away_score: number | null;
  // Knockout shootout winner (HOME/AWAY) when level at 120'; null otherwise.
  penalty_winner: string | null;
  is_finished: boolean;
  // When false the match is voided from scoring (no points), though predictions
  // and the result are still shown.
  counts_for_scoring: boolean;
  // Still open for predictions (not yet locked). Distinguishes a genuinely
  // upcoming match from one that's locked/finished but kept private by the owner.
  is_open: boolean;
  revealed: boolean;
  predicted_count: number;
  predictions: AllPredEntry[];
}

export interface AllPredictionsResp {
  reveal_predictions: boolean;
  lock_minutes: number;
  member_count: number;
  matches: AllPredMatch[];
}

export interface Profile {
  id: number;
  email: string;
  display_name: string;
  public_name: string;
  avatar: string | null;
  bio: string;
  location: string;
  social_handle: string;
  favorite_team: TeamT | null;
  joined_at: string;
}

// The signed-in user's Telegram reminder link (see TelegramConnect).
// `deep_link` is the t.me/<bot>?start=<token> URL, present only while unlinked
// and only when a bot is configured on the server (`configured`).
export interface TelegramStatus {
  configured: boolean;
  linked: boolean;
  notify: boolean;
  // Separate opt-in for live match-event DMs (kickoff, goals, half-time, full-time).
  notify_matches: boolean;
  deep_link: string | null;
}

export interface PlayerCard {
  id: number;
  public_name: string;
  avatar: string | null;
  location: string;
  favorite_team: TeamT | null;
  league_count: number;
}

export interface SharedLeague {
  slug: string;
  name: string;
  competition: string;
}

export interface PlayerDetail {
  profile: Profile;
  is_me: boolean;
  stats: { leagues: number; predictions: number };
  shared_leagues: SharedLeague[];
}

// ----- Matchday recap (the animated end-of-day story) ----------------------
// A compact fixture card (no per-viewer prediction fields).
export interface RecapMatchMini {
  id: number;
  stage: string;
  stage_label: string;
  kickoff: string;
  home_team: TeamT | null;
  away_team: TeamT | null;
  home_label: string | null;
  away_label: string | null;
  home_score: number | null;
  away_score: number | null;
}

export interface RecapDayMatch extends RecapMatchMini {
  predicted_count: number;
}

// One member's standout prediction: the fixture, their pick, and the payoff.
export interface RecapCall {
  match: RecapMatchMini;
  prediction: { home: number; away: number };
  points: number;
  tier: string;
  tier_label: string | null;
}

export interface RecapPlayer {
  id: number;
  name: string;
  avatar: string | null;
  is_me: boolean;
}

export interface RecapMe {
  participated: boolean;
  predicted: number;
  total: number;
  points: number;
  hits: {
    exact: number;
    diff: number;
    winner: number;
    participation: number;
    missed: number;
  };
  best_call: RecapCall | null;
  rank_before: number;
  rank_after: number;
  // Positive = climbed the table across the day.
  rank_delta: number;
  total_before: number;
  total_after: number;
  is_top_scorer: boolean;
  day_avg: number;
}

export interface RecapGeneral {
  top_scorer: (RecapPlayer & { points: number; ties: number }) | null;
  best_call: (RecapPlayer & RecapCall & { also_count: number }) | null;
  surprise: {
    match: RecapMatchMini;
    correct_count: number;
    predicted_count: number;
  } | null;
  // Biggest rank change each way across the day (delta is always positive).
  mover: (RecapPlayer & { from_rank: number; to_rank: number; delta: number }) | null;
  faller: (RecapPlayer & { from_rank: number; to_rank: number; delta: number }) | null;
  podium: (RecapPlayer & { rank: number; total: number })[];
}

// One row of the full day scoreboard: a member, their points earned that day,
// and how their overall rank moved (start-of-day -> end-of-day).
export interface RecapScoreRow extends RecapPlayer {
  rank_before: number;
  rank_after: number;
  total: number;
  // Cumulative table before this matchday (= total - day_points).
  total_before: number;
  day_points: number;
  // Points earned on each of the day's matches, in kickoff order (aligned with
  // RecapResp.matches) — lets the UI replay the table match by match.
  match_points: number[];
}

export interface RecapResp {
  // ISO date (YYYY-MM-DD) of the recapped matchday, or null when nothing has
  // finished yet. `available_dates` is ascending for prev/next-day navigation.
  date: string | null;
  available_dates: string[];
  matches: RecapDayMatch[];
  me: RecapMe | null;
  general: RecapGeneral | null;
  scoreboard: RecapScoreRow[];
}

// ----- Fun / novelty stats ------------------------------------------------

export interface FunMember {
  name: string;
  is_me: boolean;
}

export interface FunMemberCount extends FunMember {
  count: number;
}

export interface FunMemberGoals extends FunMember {
  avg_goals: number;
}

export interface FunMemberDraw extends FunMember {
  count: number;
  pct: number;
}

export interface FunMemberPct extends FunMember {
  pct: number;
}

export interface FunMemberMargin extends FunMember {
  avg_margin: number;
}

export interface FunBuddyPair {
  name_a: string;
  is_me_a: boolean;
  name_b: string;
  is_me_b: boolean;
  match_count: number;
  total: number;
  pct: number;
}

export interface FunScore {
  home: number;
  away: number;
  count: number;
}

export interface FunStatsResp {
  has_data: boolean;
  total_predictions?: number;
  member_count?: number;
  total_matches?: number;
  most_active?: FunMemberCount[];
  dream_goals?: FunMemberGoals[];
  lone_wolf?: FunMemberCount[];
  best_buddies?: FunBuddyPair[];
  draw_kings?: FunMemberDraw[];
  crowd_favorites?: FunScore[];
  sheep_goat?: FunMemberPct[];
  boldest?: FunMemberMargin[];
}

// ----- Points & rank progression (the player-toggle line chart) ------------
// One finished match = one x-axis step. Same compact fixture as the recap, plus
// the match number; home/away scores are filled in (a step is always finished).
export interface ProgressionStep extends RecapMatchMini {
  match_number: number | null;
}

// One player's series. `totals`/`ranks`/`match_points` are aligned with
// ProgressionResp.steps: index i is the state *after* the i-th finished match.
// `total`/`rank` are the final standing (last step), or 0/null before any match.
export interface ProgressionPlayer {
  id: number;
  name: string;
  is_me: boolean;
  totals: number[];
  ranks: number[];
  match_points: number[];
  // Cumulative predictions made per step — the average view's denominator
  // (average[i] = totals[i] / played[i]; played 0 → treat the average as 0).
  played: number[];
  total: number;
  rank: number | null;
}

export interface ProgressionResp {
  steps: ProgressionStep[];
  players: ProgressionPlayer[];
}

// A single player's average points-per-prediction over time (the profile chart).
// On a profile it pools the player's predictions across every league; the same
// shape backs the league chart's per-player average. All arrays align with steps.
export interface PlayerAverageResp {
  steps: ProgressionStep[];
  series: {
    totals: number[];
    played: number[];
    averages: number[];
  };
}

export interface MemberRow {
  rank: number;
  id: number;
  name: string;
  avatar: string | null;
  favorite_team: TeamT | null;
  role: string;
  role_label: string;
  joined_at: string;
  total: number;
  played: number;
  exact_count: number;
  is_me: boolean;
}

// ----- Tournament-wide bonus predictions -----------------------------------
// A shortlisted player (Golden Boot / Ball option).
export interface PlayerCandidateT {
  id: number;
  name: string;
  team: TeamT | null;
}

// A league member as an option for the "who wins our league" pick (the id is
// the membership id, which is what a pick's `value` references).
export interface BonusMemberT {
  id: number;
  name: string;
  is_me: boolean;
}

export interface BonusQuestionT {
  kind: string;
  label: string;
  description: string;
  // How the question is answered — decides which option list to show.
  answer_type: "team" | "player" | "member";
  points: number;
  // The current pick's option id (team / player / membership), or null.
  my_pick: number | null;
  // Once settled: the correct option id, whether my pick was right, and the
  // points I earned. All null before settlement.
  correct: number | null;
  my_correct: boolean | null;
  my_points: number | null;
}

export interface BonusResp {
  // The feature is on for this league (a lock deadline is set).
  enabled: boolean;
  // Picks can still be edited (enabled and before the deadline).
  is_open: boolean;
  lock_at: string | null;
  // Results have been computed (correct answers + points are populated).
  settled: boolean;
  teams: TeamT[];
  players: PlayerCandidateT[];
  members: BonusMemberT[];
  questions: BonusQuestionT[];
}
