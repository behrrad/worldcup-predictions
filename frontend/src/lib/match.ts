import type { TeamT } from "./types";

/**
 * Knockout = anything past the group stage. Mirrors the backend's
 * KNOCKOUT_STAGES check and the established `stage !== "GROUP"` idiom — these are
 * the only matches that can go to a penalty shootout.
 */
export function isKnockout(stage: string): boolean {
  return stage !== "GROUP";
}

/** A draw needs both scores filled in and equal (the shootout trigger). */
export function isDrawScore(home: string, away: string): boolean {
  return home !== "" && away !== "" && home === away;
}

/**
 * The team name an advancer/penalty-winner code (HOME/AWAY) points at, or null
 * when nothing was picked. Falls back to a generic side label if the team isn't
 * resolved yet (shouldn't happen once a knockout match is predictable).
 */
export function advancerTeamName(
  side: string | null | undefined,
  home: TeamT | null,
  away: TeamT | null,
): string | null {
  if (side === "HOME") return home?.name ?? "میزبان";
  if (side === "AWAY") return away?.name ?? "میهمان";
  return null;
}
