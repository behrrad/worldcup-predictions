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
        </div>
        <div className="match">
          <div className="team home">
            <span>{m.home_team?.name ?? "؟"}</span>
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
            <span>{m.away_team?.name ?? "؟"}</span>
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
        {data.revealed ? (
          <table className="table">
            <thead>
              <tr>
                <th>نام</th>
                <th>پیش‌بینی</th>
                <th>امتیاز</th>
              </tr>
            </thead>
            <tbody>
              {data.predictions.length > 0 ? (
                data.predictions.map((p, i) => (
                  <tr
                    key={i}
                    style={p.is_me ? { background: "#fffbeb" } : undefined}
                  >
                    <td>
                      {p.name}
                      {p.is_me && <span className="muted"> (تو)</span>}
                    </td>
                    <td>
                      {fa(p.home)} : {fa(p.away)}
                    </td>
                    <td className="pts">
                      {p.points !== null ? fa(p.points) : "—"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="empty">
                    کسی برای این بازی پیش‌بینی ثبت نکرده.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        ) : (
          <div className="empty">
            پیش‌بینی دیگران پس از بسته‌شدن پیش‌بینی‌ها (
            {fmtDateTime(data.lock_time)}) نمایش داده می‌شود.
          </div>
        )}
      </div>
    </>
  );
}
