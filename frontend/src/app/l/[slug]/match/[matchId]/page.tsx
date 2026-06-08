import { serverFetch } from "@/lib/server";
import { fmtDateTime, fa } from "@/lib/format";
import type { MatchDetailResp } from "@/lib/types";

export default async function MatchDetail({
  params,
}: {
  params: Promise<{ slug: string; matchId: string }>;
}) {
  const { slug, matchId } = await params;
  const data = (await serverFetch(
    `/leagues/${slug}/matches/${matchId}/`,
  )) as MatchDetailResp;
  const m = data.match;

  return (
    <>
      <div className="card">
        <div className="match-meta">
          <span className="stage-badge">{m.stage_label}</span>
          <span>{fmtDateTime(m.kickoff)}</span>
          {m.venue && <span className="muted">📍 {m.venue}</span>}
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
            ) : (
              "—"
            )}
          </div>
          <div className="team away">
            <span className="flag">{m.away_team?.flag}</span>
            <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
          </div>
        </div>
        {m.my_prediction && (
          <p className="center mt">
            پیش‌بینی تو:{" "}
            <strong>
              {fa(m.my_prediction.home)} : {fa(m.my_prediction.away)}
            </strong>
          </p>
        )}
      </div>

      <div className="card mt">
        <h2 className="card-title">پیش‌بینی همه</h2>
        <p className="muted center">
          {fa(data.predictions.length)} از {fa(data.member_count)} نفر پیش‌بینی
          کرده‌اند
        </p>
        {data.predictions.length === 0 ? (
          <div className="empty">هنوز کسی برای این بازی پیش‌بینی ثبت نکرده.</div>
        ) : (
          <>
            {!data.revealed && (
              <p className="muted center">
                نتیجهٔ پیش‌بینی‌ها پس از بسته‌شدن (
                {fmtDateTime(data.lock_time)}) نمایش داده می‌شود.
              </p>
            )}
            <table className="table">
              <thead>
                <tr>
                  <th>نام</th>
                  <th>پیش‌بینی</th>
                  {data.revealed && <th>امتیاز</th>}
                </tr>
              </thead>
              <tbody>
                {data.predictions.map((p, i) => (
                  <tr key={i} className={p.is_me ? "me-row" : undefined}>
                    <td>
                      {p.name}
                      {p.is_me && <span className="muted"> (تو)</span>}
                    </td>
                    <td>
                      {data.revealed ? (
                        `${fa(p.home!)} : ${fa(p.away!)}`
                      ) : (
                        <span className="muted" title="پس از بسته‌شدن نمایش داده می‌شود">
                          🔒
                        </span>
                      )}
                    </td>
                    {data.revealed && (
                      <td className="pts">
                        {p.points !== null ? fa(p.points) : "—"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </>
  );
}
