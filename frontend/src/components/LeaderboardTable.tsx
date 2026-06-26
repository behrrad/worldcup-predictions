"use client";

import { useState } from "react";

import { fa } from "@/lib/format";
import type { LeaderboardResp, LiveMatchInfo, LivePickT } from "@/lib/types";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

/** Returns a CSS class name reflecting the match tier at the current live score. */
function pickTier(
  pick: LivePickT,
  liveHome: number,
  liveAway: number,
): "exact" | "diff" | "winner" | "wrong" | "none" {
  if (pick.home === null || pick.away === null) return "none";
  if (pick.home === liveHome && pick.away === liveAway) return "exact";
  const pickDiff = pick.home - pick.away;
  const liveDiff = liveHome - liveAway;
  if (pickDiff === liveDiff) return "diff";
  const pickSign = Math.sign(pick.home - pick.away);
  const liveSign = Math.sign(liveHome - liveAway);
  if (pickSign === liveSign) return "winner";
  return "wrong";
}

/** Compact badge showing one member's pick for a single live match. */
function PickBadge({
  pick,
  match,
}: {
  pick: LivePickT;
  match: LiveMatchInfo;
}) {
  const tier = pickTier(pick, match.live_home, match.live_away);
  const home = match.home_team;
  const away = match.away_team;

  return (
    <span className={`pick-badge pick-badge--${tier}`} title={`${home?.name ?? "؟"} - ${away?.name ?? "؟"}`}>
      {home?.flag ?? "🏳️"}
      {pick.home !== null ? fa(pick.home) : "؟"}
      {"-"}
      {pick.away !== null ? fa(pick.away) : "؟"}
      {away?.flag ?? "🏳️"}
    </span>
  );
}

/**
 * The scoreboard with two views. «جدول رسمی» ranks by officially-recorded
 * points only; «جدول زنده» (shown — and preselected — only while a match is
 * in play) plays the current live score as if it were the final result, so
 * everyone can watch the standings move goal by goal. Live points are
 * provisional: once the official result lands, the official table takes over.
 * Data refreshes via the LiveScores strip's router.refresh on every goal.
 */
export default function LeaderboardTable({ board }: { board: LeaderboardResp }) {
  const [view, setView] = useState<"official" | "live">(
    board.is_live ? "live" : "official",
  );
  const live = view === "live" && board.is_live;

  const rows = [...board.rows].sort((a, b) =>
    live ? a.live_rank - b.live_rank : a.rank - b.rank,
  );

  const liveMatches = board.live_matches ?? [];

  return (
    <>
      {board.is_live && (
        <div className="section-tabs">
          <button
            type="button"
            className={`tab ${live ? "active" : ""}`}
            onClick={() => setView("live")}
          >
            <span className="live-dot" /> جدول زنده
          </button>
          <button
            type="button"
            className={`tab ${!live ? "active" : ""}`}
            onClick={() => setView("official")}
          >
            جدول رسمی
          </button>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>رتبه</th>
              <th>نام</th>
              <th>بازی‌ها</th>
              <th>نتیجهٔ دقیق</th>
              <th>{live ? "امتیاز زنده" : "امتیاز"}</th>
              {live && liveMatches.length > 0 && (
                <th>پیش‌بینی بازی‌های جاری</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.length > 0 ? (
              rows.map((r) => {
                const rank = live ? r.live_rank : r.rank;
                const moved = live ? r.rank - r.live_rank : 0;
                return (
                  <tr key={r.name} className={r.is_me ? "me-row" : undefined}>
                    <td className={`rank rank-${rank}`}>
                      {MEDAL[rank] ? (
                        <span className="medal">{MEDAL[rank]}</span>
                      ) : (
                        fa(rank)
                      )}
                      {moved !== 0 && (
                        <span
                          className={`rank-move ${moved > 0 ? "up" : "down"}`}
                        >
                          {moved > 0 ? "▲" : "▼"}
                        </span>
                      )}
                    </td>
                    <td>
                      {r.name}
                      {r.is_me && <span className="muted"> (تو)</span>}
                    </td>
                    <td>{fa(r.played)}</td>
                    <td>{fa(r.exact_count)}</td>
                    <td className="pts">
                      {fa(live ? r.live_total : r.total)}
                      {live && r.live_points > 0 && (
                        <span className="live-delta">{fa(r.live_points)}+</span>
                      )}
                    </td>
                    {live && liveMatches.length > 0 && (
                      <td className="live-picks-cell">
                        {liveMatches.map((m, i) => {
                          const pick = r.live_picks?.[i];
                          if (!pick) return null;
                          return (
                            <PickBadge key={m.id} pick={pick} match={m} />
                          );
                        })}
                      </td>
                    )}
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={live && liveMatches.length > 0 ? 6 : 5} className="empty">
                  هنوز امتیازی ثبت نشده است.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {live && (
          <p className="muted live-note">
            امتیازهای زنده موقتی‌اند و بر اساس نتیجهٔ فعلی بازی‌های در جریان
            محاسبه می‌شوند؛ جدول رسمی پس از ثبت نتیجهٔ نهایی به‌روز می‌شود.
          </p>
        )}
      </div>
    </>
  );
}
