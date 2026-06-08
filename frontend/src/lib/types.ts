export interface TeamT {
  id: number;
  name: string;
  name_en: string;
  code: string;
  flag: string;
  group: string;
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
  lock_time: string;
  predictions: {
    name: string;
    home: number;
    away: number;
    points: number | null;
    tier_label: string | null;
    is_me: boolean;
  }[];
}
