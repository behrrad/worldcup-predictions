/**
 * Shared SVG line-chart primitives, used by both the league progression chart
 * (ProgressionChart) and the profile average chart (ProfileAverageChart) so the
 * geometry, colours and number formatting stay identical. The viewBox is fixed
 * and the <svg> scales to its container; everything below is in viewBox units.
 */
import { fa } from "./format";
import type { ProgressionStep } from "./types";

// Plot geometry (viewBox units). Padding leaves room for the y labels on the
// left and the x labels along the bottom.
export const GEO = { W: 720, H: 380, PX0: 46, PX1: 704, PY0: 18, PY1: 340 };

// Distinct, theme-friendly hues, assigned to players by final standing so a
// player keeps the same colour across the legend, lines, dots and tooltip.
export const SERIES_COLORS = [
  "#ef3e42", "#2b6cff", "#12a45f", "#f0a500", "#9b59b6", "#e84393",
  "#0aa3a3", "#e67e22", "#3867d6", "#16a085", "#c0392b", "#8e44ad",
  "#2d98da", "#eb3b5a", "#0fb9b1", "#a55eea", "#fd9644", "#778ca3",
];

/** Round a value up to a "nice" axis maximum (1, 2, 5 × a power of ten). */
export function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

/** Persian-digit axis/value label; one decimal unless the value is whole. */
export function numLabel(v: number): string {
  return fa(Number.isInteger(v) ? String(v) : v.toFixed(1));
}

/** Evenly space step i across the plot width (centred when there's one step). */
export function xFor(i: number, n: number): number {
  const { PX0, PX1 } = GEO;
  if (n <= 1) return (PX0 + PX1) / 2;
  return PX0 + (i / (n - 1)) * (PX1 - PX0);
}

/** A compact fixture caption, e.g. «🇦🇷 ARG ۲–۱ FRA 🇫🇷». */
export function stepLabel(s: ProgressionStep): string {
  const h = s.home_team;
  const a = s.away_team;
  const hn = h?.code || h?.name || s.home_label || "؟";
  const an = a?.code || a?.name || s.away_label || "؟";
  const hf = h?.flag ? `${h.flag} ` : "";
  const af = a?.flag ? ` ${a.flag}` : "";
  return `${hf}${hn} ${fa(s.home_score ?? "")}–${fa(s.away_score ?? "")} ${an}${af}`;
}
