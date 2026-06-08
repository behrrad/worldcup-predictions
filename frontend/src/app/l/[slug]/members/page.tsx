import Link from "next/link";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import Avatar from "@/components/Avatar";
import type { MemberRow } from "@/lib/types";

export default async function MembersPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const members = (await serverFetch(`/leagues/${slug}/members/`)) as MemberRow[];

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th>رتبه</th>
            <th>بازیکن</th>
            <th>نقش</th>
            <th>بازی‌ها</th>
            <th>امتیاز</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id} className={m.is_me ? "me-row" : undefined}>
              <td className={`rank rank-${m.rank}`}>{fa(m.rank)}</td>
              <td>
                <Link href={`/players/${m.id}`} className="member-cell">
                  <Avatar src={m.avatar} name={m.name} size={34} />
                  <span>
                    {m.name}
                    {m.is_me && <span className="muted"> (تو)</span>}
                  </span>
                  {m.favorite_team && (
                    <span className="flag">{m.favorite_team.flag}</span>
                  )}
                </Link>
              </td>
              <td className="muted">{m.role_label}</td>
              <td>{fa(m.played)}</td>
              <td className="pts">{fa(m.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
