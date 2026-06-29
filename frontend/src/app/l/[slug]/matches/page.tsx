import Link from "next/link";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import { advancerTeamName } from "@/lib/match";
import { LocalDateTime } from "@/components/LocalTime";
import type { MatchT } from "@/lib/types";

export default async function Matches({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const matches = (await serverFetch(`/leagues/${slug}/matches/`)) as MatchT[];

  return (
    <div className="card">
      {matches.length > 0 ? (
        matches.map((m) => (
          <div key={m.id}>
            <div className="match-meta">
              <span className="stage-badge">{m.stage_label}</span>
              <span><LocalDateTime iso={m.kickoff} /></span>
              {m.venue && <span className="muted">📍 {m.venue}</span>}
              {m.live && (
                <span className="live-minute">
                  {m.live.status === "LIVE" && m.live.minute
                    ? `● ${fa(m.live.minute)}′ زنده`
                    : m.live.status_label}
                </span>
              )}
            </div>
            <div className="match">
              <div className="team home">
                <span>{m.home_team?.name ?? m.home_label ?? "؟"}</span>
                <span className="flag">{m.home_team?.flag}</span>
              </div>
              <div className="vs">
                {m.is_finished ? (
                  <span className="score-final">
                    {fa(m.home_score!)} : {fa(m.away_score!)}
                  </span>
                ) : m.live ? (
                  <span className="score-live">
                    {fa(m.live.home ?? "؟")} : {fa(m.live.away ?? "؟")}
                  </span>
                ) : (
                  "—"
                )}
              </div>
              <div className="team away">
                <span className="flag">{m.away_team?.flag}</span>
                <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
              </div>
            </div>
            {m.penalty_winner && (
              <p className="center muted" style={{ margin: "4px 0 0" }}>
                🥅 صعود{" "}
                {advancerTeamName(m.penalty_winner, m.home_team, m.away_team)} با
                ضربات پنالتی
              </p>
            )}
            <div className="match-meta" style={{ marginTop: 6 }}>
              <Link href={`/l/${slug}/match/${m.id}`} className="muted">
                پیش‌بینی من:{" "}
                {m.my_prediction ? (
                  <strong>
                    {fa(m.my_prediction.home)} : {fa(m.my_prediction.away)}
                    {m.my_prediction.advancer &&
                      ` ↑${advancerTeamName(m.my_prediction.advancer, m.home_team, m.away_team)}`}
                  </strong>
                ) : (
                  "—"
                )}
              </Link>
              {m.my_points !== null && (
                <span className="pts-pill">
                  {fa(m.my_points)} امتیاز · {m.tier_label}
                </span>
              )}
            </div>
            <hr
              style={{
                border: "none",
                borderTop: "1px solid var(--line)",
                margin: "14px 0",
              }}
            />
          </div>
        ))
      ) : (
        <div className="empty">هنوز بازی‌ای برای نمایش نیست.</div>
      )}
    </div>
  );
}
