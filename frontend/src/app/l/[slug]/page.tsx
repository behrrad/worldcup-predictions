import Link from "next/link";

import { serverFetch } from "@/lib/server";
import { fmtDateTime, fa } from "@/lib/format";
import type { LeagueDetail, LeaderRow, MatchT } from "@/lib/types";

export default async function Overview({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [league, board, matches] = await Promise.all([
    serverFetch(`/leagues/${slug}/`) as Promise<LeagueDetail>,
    serverFetch(`/leagues/${slug}/leaderboard/`) as Promise<LeaderRow[]>,
    serverFetch(`/leagues/${slug}/matches/`) as Promise<MatchT[]>,
  ]);

  const upcoming = matches.filter((m) => !m.is_finished).slice(0, 5);
  const top = board.slice(0, 5);

  return (
    <>
      {league.is_owner && league.invite_code && (
        <div className="card">
          <h2 className="card-title">🔗 دعوت دوستان</h2>
          <p className="muted">این کد را برای دوستانت بفرست تا به مسابقه بپیوندند:</p>
          <span className="invite-code">{league.invite_code}</span>
        </div>
      )}

      <div className="grid grid-2 mt">
        <div className="card">
          <h2 className="card-title">⏭️ بازی‌های پیش رو</h2>
          {upcoming.length > 0 ? (
            upcoming.map((m) => (
              <div key={m.id}>
                <div className="match-meta">
                  <span className="stage-badge">{m.stage_label}</span>
                  <span>{fmtDateTime(m.kickoff)}</span>
                </div>
                <div className="match">
                  <div className="team home">
                    <span>{m.home_team?.name ?? m.home_label ?? "؟"}</span>
                    <span className="flag">{m.home_team?.flag}</span>
                  </div>
                  <div className="vs">—</div>
                  <div className="team away">
                    <span className="flag">{m.away_team?.flag}</span>
                    <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="empty">بازی پیش‌رویی نیست.</div>
          )}
          <Link className="btn btn-pitch btn-block mt" href={`/l/${slug}/predictions`}>
            ثبت پیش‌بینی
          </Link>
        </div>

        <div className="card">
          <h2 className="card-title">🏅 صدر جدول</h2>
          <table className="table">
            <tbody>
              {top.length > 0 ? (
                top.map((r) => (
                  <tr key={r.rank + r.name}>
                    <td className={`rank rank-${r.rank}`}>{fa(r.rank)}</td>
                    <td>{r.name}</td>
                    <td className="pts">{fa(r.total)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="empty" colSpan={3}>
                    هنوز امتیازی ثبت نشده.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Link className="btn btn-outline btn-block mt" href={`/l/${slug}/leaderboard`}>
            جدول کامل
          </Link>
        </div>
      </div>
    </>
  );
}
