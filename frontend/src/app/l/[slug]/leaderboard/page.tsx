import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import type { LeaderRow } from "@/lib/types";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default async function Leaderboard({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const board = (await serverFetch(`/leagues/${slug}/leaderboard/`)) as LeaderRow[];

  return (
    <div className="card">
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
          {board.length > 0 ? (
            board.map((r) => (
              <tr
                key={r.rank + r.name}
                style={r.is_me ? { background: "#fffbeb" } : undefined}
              >
                <td className={`rank rank-${r.rank}`}>
                  {MEDAL[r.rank] ? (
                    <span className="medal">{MEDAL[r.rank]}</span>
                  ) : (
                    fa(r.rank)
                  )}
                </td>
                <td>
                  {r.name}
                  {r.is_me && <span className="muted"> (تو)</span>}
                </td>
                <td>{fa(r.played)}</td>
                <td>{fa(r.exact_count)}</td>
                <td className="pts">{fa(r.total)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} className="empty">
                هنوز امتیازی ثبت نشده است.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
