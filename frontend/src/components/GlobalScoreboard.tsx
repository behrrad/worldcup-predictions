"use client";

import { useState } from "react";

import { fa } from "@/lib/format";
import type { GlobalScoreboardResp } from "@/lib/types";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

function RankCell({ rank }: { rank: number }) {
  return (
    <td className={`rank rank-${rank}`}>
      {MEDAL[rank] ? <span className="medal">{MEDAL[rank]}</span> : fa(rank)}
    </td>
  );
}

/**
 * The site-wide scoreboard with three views, all on the "fair" scale: every
 * prediction is scored on the default ladder (10/7/5/2) with a ×1 multiplier
 * for every match — no per-league point configs, knockout multipliers, or the
 * 2× boost — so players and leagues across the whole site are comparable.
 *
 * «جدول کل» ranks every player by fair total points; «میانگین امتیاز» ranks by
 * average points per predicted game, limited to players who predicted at least
 * half of the finished matches; «میانگین لیگ‌ها» ranks each league by the mean
 * of its eligible members' averages.
 */
export default function GlobalScoreboard({
  board,
}: {
  board: GlobalScoreboardResp;
}) {
  const [view, setView] = useState<"total" | "average" | "leagues">("total");

  const totalRows = [...board.players].sort((a, b) => a.rank - b.rank);
  const avgRows = board.players
    .filter((p) => p.eligible_for_avg)
    .sort((a, b) => (a.avg_rank ?? 0) - (b.avg_rank ?? 0));
  const leagueRows = board.leagues;

  return (
    <>
      <div className="section-tabs">
        <button
          type="button"
          className={`tab ${view === "total" ? "active" : ""}`}
          onClick={() => setView("total")}
        >
          جدول کل
        </button>
        <button
          type="button"
          className={`tab ${view === "average" ? "active" : ""}`}
          onClick={() => setView("average")}
        >
          میانگین امتیاز
        </button>
        <button
          type="button"
          className={`tab ${view === "leagues" ? "active" : ""}`}
          onClick={() => setView("leagues")}
        >
          میانگین لیگ‌ها
        </button>
      </div>

      <div className="card">
        {view === "total" && (
          <table className="table">
            <thead>
              <tr>
                <th>رتبه</th>
                <th>نام</th>
                <th>بازی‌ها</th>
                <th>نتیجهٔ دقیق</th>
                <th>امتیاز</th>
              </tr>
            </thead>
            <tbody>
              {totalRows.length > 0 ? (
                totalRows.map((p) => (
                  <tr key={p.user_id} className={p.is_me ? "me-row" : undefined}>
                    <RankCell rank={p.rank} />
                    <td>
                      {p.name}
                      {p.is_me && <span className="muted"> (تو)</span>}
                    </td>
                    <td>{fa(p.played)}</td>
                    <td>{fa(p.exact_count)}</td>
                    <td className="pts">{fa(p.total)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="empty">
                    هنوز بازیکنی در پیش‌بینی‌ها شرکت نکرده است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        {view === "average" && (
          <table className="table">
            <thead>
              <tr>
                <th>رتبه</th>
                <th>نام</th>
                <th>بازی‌ها</th>
                <th>امتیاز کل</th>
                <th>میانگین هر بازی</th>
              </tr>
            </thead>
            <tbody>
              {avgRows.length > 0 ? (
                avgRows.map((p) => (
                  <tr key={p.user_id} className={p.is_me ? "me-row" : undefined}>
                    <RankCell rank={p.avg_rank ?? 0} />
                    <td>
                      {p.name}
                      {p.is_me && <span className="muted"> (تو)</span>}
                    </td>
                    <td>{fa(p.played)}</td>
                    <td className="pts">{fa(p.total)}</td>
                    <td className="pts">{fa(p.avg_points.toFixed(4))}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="empty">
                    هنوز کسی حداقل نیمی از بازی‌های انجام‌شده را پیش‌بینی نکرده
                    است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        {view === "leagues" && (
          <table className="table">
            <thead>
              <tr>
                <th>رتبه</th>
                <th>مسابقه</th>
                <th>اعضا</th>
                <th>اعضای فعال</th>
                <th>میانگین امتیاز</th>
              </tr>
            </thead>
            <tbody>
              {leagueRows.length > 0 ? (
                leagueRows.map((l) => (
                  <tr key={l.id}>
                    {l.rank !== null ? (
                      <RankCell rank={l.rank} />
                    ) : (
                      <td className="rank">—</td>
                    )}
                    <td>{l.name}</td>
                    <td>{fa(l.member_count)}</td>
                    <td>{fa(l.eligible_count)}</td>
                    <td className="pts">
                      {l.avg_points !== null ? fa(l.avg_points.toFixed(4)) : "—"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="empty">
                    هنوز مسابقه‌ای ساخته نشده است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        <p className="muted live-note">
          {view === "leagues"
            ? "میانگین هر مسابقه، میانگینِ «میانگین امتیاز هر بازی» اعضای فعال آن است — اعضایی که دست‌کم نیمی از بازی‌های انجام‌شده را پیش‌بینی کرده‌اند. امتیازها برای مقایسهٔ منصفانه با ضریب ×۱ و امتیازدهی پیش‌فرض (۱۰/۷/۵/۲) حساب شده‌اند."
            : view === "average"
              ? "میانگین امتیازی که هر نفر در هر بازیِ پیش‌بینی‌کرده گرفته است؛ فقط بازیکنانی که دست‌کم نیمی از بازی‌های انجام‌شده را پیش‌بینی کرده‌اند نمایش داده می‌شوند. امتیازها با ضریب ×۱ و امتیازدهی پیش‌فرض (۱۰/۷/۵/۲) حساب شده‌اند."
              : "برای مقایسهٔ منصفانه میان همهٔ بازیکنان سایت، امتیاز همهٔ بازی‌ها با ضریب ×۱ و امتیازدهی پیش‌فرض (۱۰/۷/۵/۲) حساب شده است — بدون ضریب مراحل حذفی و تنظیمات اختصاصی هر مسابقه. اگر کسی یک بازی را در چند مسابقه پیش‌بینی کرده باشد، فقط اولین پیش‌بینی‌اش حساب می‌شود."}
        </p>
      </div>
    </>
  );
}
