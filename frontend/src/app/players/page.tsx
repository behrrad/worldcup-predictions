import Link from "next/link";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import Avatar from "@/components/Avatar";
import type { PlayerCard } from "@/lib/types";

export default async function PlayersPage() {
  const players = (await serverFetch("/players/")) as PlayerCard[];

  return (
    <>
      <div className="page-head">
        <h1>بازیکنان</h1>
        <p>همهٔ کسانی که در پیش‌بینی‌ها شرکت دارند</p>
      </div>

      {players.length > 0 ? (
        <div className="players-grid">
          {players.map((p) => (
            <Link key={p.id} href={`/players/${p.id}`} className="card player-card">
              <Avatar src={p.avatar} name={p.public_name} size={72} />
              <strong>{p.public_name}</strong>
              {p.favorite_team && (
                <span className="muted">
                  {p.favorite_team.flag} {p.favorite_team.name}
                </span>
              )}
              {p.location && <span className="muted">📍 {p.location}</span>}
              <span className="player-leagues">{fa(p.league_count)} مسابقه</span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="empty">هنوز بازیکنی ثبت‌نام نکرده است.</div>
      )}
    </>
  );
}
