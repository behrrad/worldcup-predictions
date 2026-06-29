import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import { advancerTeamName } from "@/lib/match";
import Avatar from "@/components/Avatar";
import { LocalDateTime } from "@/components/LocalTime";
import type {
  AllPredictionsResp,
  AllPredMatch,
  AllPredEntry,
  TeamT,
} from "@/lib/types";

// Maps a scoring tier to the chip accent used once a match is finished.
const TIER_CLASS: Record<string, string> = {
  EXACT: "tier-exact",
  DIFF: "tier-diff",
  WINNER: "tier-winner",
};

function Chip({
  p,
  revealed,
  home,
  away,
}: {
  p: AllPredEntry;
  revealed: boolean;
  home: TeamT | null;
  away: TeamT | null;
}) {
  const tier = revealed && p.tier ? (TIER_CLASS[p.tier] ?? "") : "";
  return (
    <span className={`pred-chip ${p.is_me ? "me" : ""} ${tier}`}>
      <Avatar src={p.avatar} name={p.name} size={22} />
      <span className="who">
        {p.name}
        {p.is_me && <span className="muted"> (تو)</span>}
      </span>
      <span className="pick">
        {revealed ? (
          <>
            {fa(p.home!)} : {fa(p.away!)}
            {p.advancer && ` ↑${advancerTeamName(p.advancer, home, away)}`}
          </>
        ) : (
          "🔒"
        )}
      </span>
      {revealed && p.points !== null && (
        <span className="chip-pts">{fa(p.points)}</span>
      )}
    </span>
  );
}

function MatchCard({ m, memberCount }: { m: AllPredMatch; memberCount: number }) {
  return (
    <div className="card mt allpred-card">
      <div className="match-meta">
        <span className="stage-badge">{m.stage_label}</span>
        <span><LocalDateTime iso={m.kickoff} /></span>
        {m.revealed ? (
          <span className="lock-open">نمایش داده شد</span>
        ) : m.is_open ? (
          <span className="muted">🔒 هنوز قفل نشده</span>
        ) : (
          <span className="muted">🔒 خصوصی</span>
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
          {advancerTeamName(m.penalty_winner, m.home_team, m.away_team)} با ضربات
          پنالتی
        </p>
      )}

      {m.predictions.length === 0 ? (
        <div className="empty">هنوز کسی برای این بازی پیش‌بینی ثبت نکرده.</div>
      ) : (
        <div className="pred-chips">
          {m.predictions.map((p, i) => (
            <Chip
              key={i}
              p={p}
              revealed={m.revealed}
              home={m.home_team}
              away={m.away_team}
            />
          ))}
        </div>
      )}

      <p className="muted center allpred-count">
        {fa(m.predicted_count)} از {fa(memberCount)} نفر پیش‌بینی کرده‌اند
      </p>
    </div>
  );
}

export default async function AllPredictions({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = (await serverFetch(
    `/leagues/${slug}/all-predictions/`,
  )) as AllPredictionsResp;

  // Matches arrive in kickoff order. Three buckets:
  //  - revealed: locked + reveal on → picks shown (newest first)
  //  - private: locked/finished but the owner turned reveal off → picks hidden
  //  - upcoming: still open for predictions → picks hidden until lock
  const revealed = data.matches.filter((m) => m.revealed).reverse();
  const privateLocked = data.matches
    .filter((m) => !m.revealed && !m.is_open)
    .reverse();
  const upcoming = data.matches.filter((m) => m.is_open);

  return (
    <>
      <div className="card">
        <h2 className="card-title">👁️ پیش‌بینی همه</h2>
        <p className="muted">
          پیش‌بینی هر کس برای هر بازی همین‌جا جمع شده است. پیش‌بینی‌ها{" "}
          <strong>
            {data.lock_minutes > 0
              ? `${fa(data.lock_minutes)} دقیقه پیش از شروع`
              : "هنگام شروع"}
          </strong>{" "}
          هر بازی (هنگام قفل‌شدن) برای همه نمایش داده می‌شوند؛ پیش از آن فقط می‌بینی چه کسی
          پیش‌بینی کرده، نه چه چیزی.
          {!data.reveal_predictions &&
            " مدیر این مسابقه نمایش پیش‌بینی دیگران را خاموش کرده است؛ پیش‌بینی‌ها خصوصی می‌مانند."}
        </p>
        <div className="pred-legend">
          <span className="pred-chip tier-exact">
            <span className="pick">۲:۱</span>
            <span className="who">نتیجهٔ دقیق</span>
          </span>
          <span className="pred-chip tier-diff">
            <span className="pick">۲:۱</span>
            <span className="who">برنده + اختلاف</span>
          </span>
          <span className="pred-chip tier-winner">
            <span className="pick">۲:۱</span>
            <span className="who">برندهٔ درست</span>
          </span>
        </div>
      </div>

      {data.matches.length === 0 && (
        <div className="card mt empty">هنوز بازی‌ای برای نمایش نیست.</div>
      )}

      {revealed.length > 0 && (
        <>
          <div className="day-header mt">✅ بازی‌های نمایش‌داده‌شده</div>
          {revealed.map((m) => (
            <MatchCard key={m.id} m={m} memberCount={data.member_count} />
          ))}
        </>
      )}

      {privateLocked.length > 0 && (
        <>
          <div className="day-header mt">
            🔒 پیش‌بینی‌ها خصوصی‌اند (مدیر نمایش پیش‌بینی دیگران را خاموش کرده)
          </div>
          {privateLocked.map((m) => (
            <MatchCard key={m.id} m={m} memberCount={data.member_count} />
          ))}
        </>
      )}

      {upcoming.length > 0 && (
        <>
          <div className="day-header mt">⏳ بازی‌های پیش‌رو (پیش‌بینی‌ها هنوز پنهان‌اند)</div>
          {upcoming.map((m) => (
            <MatchCard key={m.id} m={m} memberCount={data.member_count} />
          ))}
        </>
      )}
    </>
  );
}
