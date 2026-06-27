import Link from "next/link";
import { notFound } from "next/navigation";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import Avatar from "@/components/Avatar";
import ProfileAverageChart from "@/components/ProfileAverageChart";
import type { PlayerAverageResp, PlayerDetail } from "@/lib/types";

export default async function PlayerProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let data: PlayerDetail | null = null;
  try {
    data = (await serverFetch(`/players/${id}/`)) as PlayerDetail;
  } catch {
    data = null;
  }
  if (!data) notFound();

  // The player's average-points-per-prediction trend, across all their leagues.
  let avg: PlayerAverageResp | null = null;
  try {
    avg = (await serverFetch(`/players/${id}/average/`)) as PlayerAverageResp;
  } catch {
    avg = null;
  }

  const p = data.profile;

  return (
    <>
      <div className="profile-head card">
        <Avatar src={p.avatar} name={p.public_name} size={96} />
        <div className="profile-head-info">
          <h1>{p.public_name}</h1>
          {p.favorite_team && (
            <div className="muted">
              تیم محبوب: {p.favorite_team.flag} {p.favorite_team.name}
            </div>
          )}
          {p.location && <div className="muted">📍 {p.location}</div>}
          {p.social_handle && <div className="muted">🔗 {p.social_handle}</div>}
          {data.is_me && (
            <Link className="btn btn-outline btn-sm mt" href="/profile">
              ویرایش پروفایل
            </Link>
          )}
        </div>
      </div>

      {p.bio && (
        <div className="card mt">
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{p.bio}</p>
        </div>
      )}

      <div className="grid grid-2 mt">
        <div className="card stat">
          <div className="num">{fa(data.stats.leagues)}</div>
          <div className="label">مسابقه</div>
        </div>
        <div className="card stat">
          <div className="num">{fa(data.stats.predictions)}</div>
          <div className="label">پیش‌بینی</div>
        </div>
      </div>

      {avg && avg.steps.length > 0 && (
        <div className="card mt">
          <h2 className="card-title">📈 روند میانگین امتیاز</h2>
          <ProfileAverageChart data={avg} />
        </div>
      )}

      {data.shared_leagues.length > 0 && (
        <div className="card mt">
          <h2 className="card-title">🏆 مسابقه‌های مشترک</h2>
          <div className="grid grid-2">
            {data.shared_leagues.map((l) => (
              <Link key={l.slug} className="card tile" href={`/l/${l.slug}`}>
                <strong>{l.name}</strong>
                <div className="muted">{l.competition}</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
