import Link from "next/link";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import { LocalDateTime } from "@/components/LocalTime";
import RevealToggle from "@/components/RevealToggle";
import type { LeagueDetail, LeaderboardResp, MatchT } from "@/lib/types";

export default async function Overview({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [league, board, matches] = await Promise.all([
    serverFetch(`/leagues/${slug}/`) as Promise<LeagueDetail>,
    serverFetch(`/leagues/${slug}/leaderboard/`) as Promise<LeaderboardResp>,
    serverFetch(`/leagues/${slug}/matches/`) as Promise<MatchT[]>,
  ]);

  const upcoming = matches.filter((m) => !m.is_finished).slice(0, 5);
  const top = board.rows.slice(0, 5);

  return (
    <>
      {league.is_owner && league.invite_code && (
        <div className="card">
          <h2 className="card-title">🔗 دعوت دوستان</h2>
          <p className="muted">این کد را برای دوستانت بفرست تا به مسابقه بپیوندند:</p>
          <span className="invite-code">{league.invite_code}</span>
        </div>
      )}

      {league.is_owner && (
        <div className="mt">
          <RevealToggle slug={slug} initial={league.reveal_predictions} />
        </div>
      )}

      <div className="card mt">
        <h2 className="card-title">📊 خروجی نتایج (اکسل)</h2>
        <p className="muted">
          فایل اکسل نتایج و پیش‌بینی‌ها را دانلود کن. پیش‌بینی بازی‌هایی که هنوز
          شروع نشده‌اند در فایل پنهان می‌ماند.
        </p>
        <a className="btn btn-outline btn-block mt" href={league.export_url} download>
          دانلود فایل اکسل
        </a>
      </div>

      <div className="grid grid-2 mt">
        <div className="card">
          <h2 className="card-title">⏭️ بازی‌های پیش رو</h2>
          {upcoming.length > 0 ? (
            upcoming.map((m) => (
              <div key={m.id}>
                <div className="match-meta">
                  <span className="stage-badge">{m.stage_label}</span>
                  <span><LocalDateTime iso={m.kickoff} /></span>
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
            <div className="empty">فعلاً بازی‌ای پیش رو نیست.</div>
          )}
          <Link className="btn btn-pitch btn-block mt" href={`/l/${slug}/predictions`}>
            ثبت پیش‌بینی
          </Link>
          <Link className="btn btn-outline btn-block mt" href={`/l/${slug}/all-predictions`}>
            👁️ پیش‌بینی همه را ببین
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
                    هنوز امتیازی ثبت نشده است.
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
