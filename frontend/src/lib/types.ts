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
