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
  // Live (in-play) state, or null when the match isn't being played right now.
  live: LiveInfoT | null;
  is_finished: boolean;
  is_open: boolean;
  can_predict: boolean;
  lock_time: string;
  my_prediction: { home: number; away: number } | null;
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
  };
}

export interface LeaderRow {
  rank: number;
  name: string;
  total: number;
  played: number;
  exact_count: number;
  is_me: boolean;
  // Live view: official total plus provisional points from in-play matches
  // (the current live score played as the final result). When nothing is
  // live these mirror the official fields.
  live_rank: number;
  live_total: number;
  live_points: number;
}

export interface LeaderboardResp {
  // True while at least one match is in play — the live view then differs
  // from the official one and the UI shows both tabs.
  is_live: boolean;
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
  is_finished: boolean;
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
  mover: (RecapPlayer & { from_rank: number; to_rank: number; delta: number }) | null;
  podium: (RecapPlayer & { rank: number; total: number })[];
}

export interface RecapResp {
  // ISO date (YYYY-MM-DD) of the recapped matchday, or null when nothing has
  // finished yet. `available_dates` is ascending for prev/next-day navigation.
  date: string | null;
  available_dates: string[];
  matches: RecapDayMatch[];
  me: RecapMe | null;
  general: RecapGeneral | null;
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
