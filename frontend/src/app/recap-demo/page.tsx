// TEMPORARY visual demo of the matchday recap story (throwaway — not for the PR).
// Feeds the real <RecapStory> realistic mock data so the animations can be seen
// without Clerk auth or the Django API.
import RecapStory from "@/components/RecapStory";
import type { RecapResp, TeamT } from "@/lib/types";

const team = (name: string, code: string, flag: string, group = "A"): TeamT => ({
  id: code.length, name, name_en: code, code, flag, group,
});

const BRA = team("برزیل", "BRA", "🇧🇷");
const ARG = team("آرژانتین", "ARG", "🇦🇷");
const FRA = team("فرانسه", "FRA", "🇫🇷");
const ESP = team("اسپانیا", "ESP", "🇪🇸");
const MAR = team("مراکش", "MAR", "🇲🇦");
const POR = team("پرتغال", "POR", "🇵🇹");

const mini = (
  id: number, home: TeamT, away: TeamT, hs: number, as_: number,
) => ({
  id, stage: "GROUP", stage_label: "مرحله گروهی",
  kickoff: "2026-06-13T18:00:00Z",
  home_team: home, away_team: away, home_label: null, away_label: null,
  home_score: hs, away_score: as_,
});

const recap: RecapResp = {
  date: "2026-06-13",
  available_dates: ["2026-06-13"],
  matches: [
    { ...mini(1, BRA, ARG, 2, 1), predicted_count: 6 },
    { ...mini(2, FRA, ESP, 0, 0), predicted_count: 6 },
    { ...mini(3, MAR, POR, 1, 0), predicted_count: 6 },
  ],
  me: {
    participated: true,
    predicted: 3,
    total: 3,
    points: 19,
    hits: { exact: 1, diff: 1, winner: 0, participation: 1, missed: 0 },
    best_call: {
      match: mini(1, BRA, ARG, 2, 1),
      prediction: { home: 2, away: 1 },
      points: 10,
      tier: "EXACT",
      tier_label: "نتیجهٔ دقیق",
    },
    rank_before: 4,
    rank_after: 2,
    rank_delta: 2,
    total_before: 28,
    total_after: 47,
    is_top_scorer: false,
    day_avg: 11.5,
  },
  general: {
    top_scorer: {
      id: 2, name: "علی", avatar: null, is_me: false, points: 24, ties: 0,
    },
    best_call: {
      id: 3, name: "سارا", avatar: null, is_me: false,
      match: mini(3, MAR, POR, 1, 0),
      prediction: { home: 1, away: 0 },
      points: 10, tier: "EXACT", tier_label: "نتیجهٔ دقیق", also_count: 0,
    },
    surprise: {
      match: mini(3, MAR, POR, 1, 0), correct_count: 1, predicted_count: 6,
    },
    mover: {
      id: 1, name: "بهراد", avatar: null, is_me: true,
      from_rank: 4, to_rank: 2, delta: 2,
    },
    podium: [
      { id: 2, name: "علی", avatar: null, is_me: false, rank: 1, total: 52 },
      { id: 1, name: "بهراد", avatar: null, is_me: true, rank: 2, total: 47 },
      { id: 4, name: "رضا", avatar: null, is_me: false, rank: 3, total: 41 },
    ],
  },
};

export default function RecapDemoPage() {
  return <RecapStory slug="demo" recap={recap} staticAll />;
}
