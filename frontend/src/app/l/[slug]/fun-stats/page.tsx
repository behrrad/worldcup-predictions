import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import type {
  FunBuddyPair,
  FunMember,
  FunMemberCount,
  FunMemberDraw,
  FunMemberGoals,
  FunMemberMargin,
  FunMemberPct,
  FunScore,
  FunStatsResp,
} from "@/lib/types";

export default async function FunStatsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = (await serverFetch(`/leagues/${slug}/fun-stats/`)) as FunStatsResp;

  if (!data.has_data) {
    return (
      <div className="card empty">
        وقتی شرکت‌کننده‌ها شروع به ثبت پیش‌بینی کنند، آمار جالب اینجا نمایش داده می‌شود.
      </div>
    );
  }

  return (
    <div className="fun-stats">
      <div className="grid grid-2">
        {/* ---- Most Active ---- */}
        <StatCard title="فعال‌ترین" icon="📋">
          <RankedList
            rows={data.most_active ?? []}
            value={(r) => `${fa(r.count)} پیش‌بینی`}
            highlight={(r) => r.count === (data.most_active?.[0]?.count ?? -1)}
          />
        </StatCard>

        {/* ---- Draw Kings ---- */}
        <StatCard title="پادشاه تساوی" icon="🤝">
          <RankedList
            rows={data.draw_kings ?? []}
            value={(r) => `${fa(r.count)} تساوی · ${fa(r.pct)}٪`}
            highlight={(r) => r.count === (data.draw_kings?.[0]?.count ?? -1) && r.count > 0}
          />
        </StatCard>

        {/* ---- Dream Goals ---- */}
        <StatCard
          title="پیش‌بینی‌گر گل‌های خیالی"
          icon="⚽"
          subtitle="بیشترین گل‌های پیش‌بینی‌شده در هر بازی"
        >
          <GoalExtremesCard
            rows={data.dream_goals ?? []}
          />
        </StatCard>

        {/* ---- Boldest ---- */}
        <StatCard
          title="جرئت‌مندترین"
          icon="🎯"
          subtitle="بزرگ‌ترین اختلاف گل میانگین در پیش‌بینی‌ها"
        >
          <RankedList
            rows={data.boldest ?? []}
            value={(r) => `${fa(r.avg_margin)} گل اختلاف`}
            highlight={(r) => r.avg_margin === (data.boldest?.[0]?.avg_margin ?? -1)}
          />
        </StatCard>

        {/* ---- Lone Wolf ---- */}
        <StatCard
          title="تنهاترین پیشگو"
          icon="🐺"
          subtitle="بیشترین پیش‌بینی منحصربه‌فردی که کس دیگری همین نتیجه را نداد"
        >
          <RankedList
            rows={data.lone_wolf ?? []}
            value={(r) => `${fa(r.count)} پیش‌بینی منحصربه‌فرد`}
            highlight={(r) => r.count === (data.lone_wolf?.[0]?.count ?? -1) && r.count > 0}
          />
        </StatCard>

        {/* ---- Sheep vs Goat ---- */}
        <StatCard
          title="گله‌دار و گرگ"
          icon="🐑"
          subtitle="درصد توافق با محبوب‌ترین پیش‌بینی بقیه در هر بازی"
        >
          <SheepGoatCard rows={data.sheep_goat ?? []} />
        </StatCard>

        {/* ---- Best Buddies ---- */}
        <StatCard
          title="شبیه‌ترین به هم"
          icon="👯"
          subtitle="زوج‌هایی که بیشترین پیش‌بینی یکسان داشتند"
        >
          <BuddiesCard rows={data.best_buddies ?? []} />
        </StatCard>

        {/* ---- Crowd Favorites ---- */}
        <StatCard
          title="محبوب‌ترین نتیجه‌ها"
          icon="🏆"
          subtitle="پرتکرارترین نتایجی که بازیکنان پیش‌بینی کردند"
        >
          <CrowdFavoritesCard scores={data.crowd_favorites ?? []} />
        </StatCard>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------- //
// Card shell
// -------------------------------------------------------------------------- //
function StatCard({
  title,
  icon,
  subtitle,
  children,
}: {
  title: string;
  icon: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <h3 className="card-title">
        <span className="fs-icon">{icon}</span>
        {title}
      </h3>
      {subtitle && <p className="muted fun-subtitle">{subtitle}</p>}
      {children}
    </div>
  );
}

// -------------------------------------------------------------------------- //
// Generic ranked list
// -------------------------------------------------------------------------- //
function RankedList<T extends FunMember>({
  rows,
  value,
  highlight,
}: {
  rows: T[];
  value: (r: T) => string;
  highlight?: (r: T) => boolean;
}) {
  if (rows.length === 0) {
    return <p className="muted">داده‌ای موجود نیست.</p>;
  }
  return (
    <ol className="fun-ranked-list">
      {rows.map((r, i) => (
        <li
          key={r.name + i}
          className={[
            "fun-ranked-item",
            r.is_me ? "me-row" : "",
            highlight?.(r) ? "fun-top" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <span className="fun-rank">{fa(i + 1)}</span>
          <span className="fun-name">
            {r.name}
            {r.is_me && <span className="muted"> (تو)</span>}
          </span>
          <span className="fun-value">{value(r)}</span>
        </li>
      ))}
    </ol>
  );
}

// -------------------------------------------------------------------------- //
// Dream goals: most optimistic at top, most pessimistic at bottom
// -------------------------------------------------------------------------- //
function GoalExtremesCard({ rows }: { rows: FunMemberGoals[] }) {
  if (rows.length === 0) return <p className="muted">داده‌ای موجود نیست.</p>;
  const top3 = rows.slice(0, 3);
  const bottom3 = rows.length > 3 ? rows.slice(-3).reverse() : [];
  return (
    <div>
      <p className="fun-section-label">خوش‌بینانه‌ترین ⬆️</p>
      <ol className="fun-ranked-list">
        {top3.map((r, i) => (
          <li key={r.name + "t" + i} className={`fun-ranked-item${r.is_me ? " me-row" : ""}${i === 0 ? " fun-top" : ""}`}>
            <span className="fun-rank">{fa(i + 1)}</span>
            <span className="fun-name">{r.name}{r.is_me && <span className="muted"> (تو)</span>}</span>
            <span className="fun-value">{fa(r.avg_goals)} گل/بازی</span>
          </li>
        ))}
      </ol>
      {bottom3.length > 0 && (
        <>
          <p className="fun-section-label" style={{ marginTop: 14 }}>بدبینانه‌ترین ⬇️</p>
          <ol className="fun-ranked-list">
            {bottom3.map((r, i) => (
              <li key={r.name + "b" + i} className={`fun-ranked-item${r.is_me ? " me-row" : ""}`}>
                <span className="fun-rank">…</span>
                <span className="fun-name">{r.name}{r.is_me && <span className="muted"> (تو)</span>}</span>
                <span className="fun-value">{fa(r.avg_goals)} گل/بازی</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

// -------------------------------------------------------------------------- //
// Sheep vs Goat: most agreeable (sheep) → most contrarian (goat)
// -------------------------------------------------------------------------- //
function SheepGoatCard({ rows }: { rows: FunMemberPct[] }) {
  if (rows.length === 0) return <p className="muted">داده‌ای موجود نیست.</p>;
  return (
    <ol className="fun-ranked-list">
      {rows.map((r, i) => {
        const isSheep = i === 0;
        const isGoat = i === rows.length - 1 && rows.length > 1;
        return (
          <li
            key={r.name + i}
            className={["fun-ranked-item", r.is_me ? "me-row" : ""].filter(Boolean).join(" ")}
          >
            <span className="fun-rank">{isSheep ? "🐑" : isGoat ? "🐺" : fa(i + 1)}</span>
            <span className="fun-name">
              {r.name}
              {r.is_me && <span className="muted"> (تو)</span>}
            </span>
            <span className="fun-value">{fa(r.pct)}٪ توافق</span>
          </li>
        );
      })}
    </ol>
  );
}

// -------------------------------------------------------------------------- //
// Best buddies pairs
// -------------------------------------------------------------------------- //
function BuddiesCard({ rows }: { rows: FunBuddyPair[] }) {
  if (rows.length === 0) return <p className="muted">هنوز زوجی با پیش‌بینی‌های مشترک کافی پیدا نشده است.</p>;
  return (
    <ol className="fun-ranked-list">
      {rows.map((r, i) => (
        <li
          key={r.name_a + r.name_b + i}
          className={["fun-ranked-item", r.is_me_a || r.is_me_b ? "me-row" : ""].filter(Boolean).join(" ")}
        >
          <span className="fun-rank">{fa(i + 1)}</span>
          <span className="fun-name fun-buddy-names">
            <span className={r.is_me_a ? "fun-me" : ""}>{r.name_a}</span>
            <span className="fun-buddy-sep">+</span>
            <span className={r.is_me_b ? "fun-me" : ""}>{r.name_b}</span>
          </span>
          <span className="fun-value">{fa(r.pct)}٪ · {fa(r.match_count)} از {fa(r.total)}</span>
        </li>
      ))}
    </ol>
  );
}

// -------------------------------------------------------------------------- //
// Crowd favorites: pill grid of scorelines
// -------------------------------------------------------------------------- //
function CrowdFavoritesCard({ scores }: { scores: FunScore[] }) {
  if (scores.length === 0) return <p className="muted">داده‌ای موجود نیست.</p>;
  const max = scores[0]?.count ?? 1;
  return (
    <div className="fun-scores-grid">
      {scores.map((s, i) => (
        <div key={i} className={`fun-score-pill${i === 0 ? " fun-score-top" : ""}`}>
          <span className="fun-score-line">{fa(s.home)}–{fa(s.away)}</span>
          <span className="fun-score-count">{fa(s.count)}×</span>
          <div
            className="fun-score-bar"
            style={{ width: `${Math.round((s.count / max) * 100)}%` }}
          />
        </div>
      ))}
    </div>
  );
}
