import Link from "next/link";
import { currentUser } from "@clerk/nextjs/server";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import JoinLeague from "@/components/JoinLeague";
import LiveScores from "@/components/LiveScores";
import SiteNotice from "@/components/SiteNotice";
import TelegramConnect from "@/components/TelegramConnect";
import type { LeagueCard, CompetitionT, MeT } from "@/lib/types";

export default async function Dashboard() {
  const [leagues, competitions, me, user] = await Promise.all([
    serverFetch("/leagues/") as Promise<LeagueCard[]>,
    serverFetch("/competitions/") as Promise<CompetitionT[]>,
    serverFetch("/me/") as Promise<MeT>,
    currentUser(),
  ]);

  const name = user?.firstName || user?.username || "دوست من";
  const hasCompetitions = competitions.length > 0;

  return (
    <>
      <div className="page-head">
        <h1>سلام {name} 👋</h1>
        <p>مسابقه‌های پیش‌بینی تو</p>
      </div>

      <SiteNotice />

      <LiveScores />

      <TelegramConnect variant="banner" />

      <Link className="card tile" href="/scoreboard">
        <strong>🌍 جدول کل بازیکنان سایت</strong>
        <div className="muted">
          رتبه‌بندی همهٔ بازیکنان روی یک مقیاس منصفانه (ضریب ×۱ برای همهٔ
          بازی‌ها) — به‌همراه میانگین امتیاز هر بازیکن و رتبه‌بندی لیگ‌ها.
        </div>
      </Link>

      {me.is_admin && (
        <Link className="card tile" href="/admin/results">
          <strong>🧮 ورود نتایج بازی‌ها (مدیر)</strong>
          <div className="muted">
            نتیجهٔ بازی‌ها را وارد کن تا امتیاز همه به‌روزرسانی شود.
          </div>
        </Link>
      )}

      {me.is_admin && (
        <Link className="card tile" href="/admin/bonus">
          <strong>🏆 ثبت پیش‌بینی‌های ویژه (مدیر)</strong>
          <div className="muted">
            پیش‌بینی‌های ویژهٔ قهرمانی را به‌جای اعضا وارد کن.
          </div>
        </Link>
      )}

      <div className="grid grid-2">
        <div className="card">
          <h2 className="card-title">🔑 پیوستن به مسابقه</h2>
          <JoinLeague />
        </div>
        <div className="card">
          <h2 className="card-title">➕ ساخت مسابقهٔ جدید</h2>
          <p className="muted">
            یک مسابقهٔ جدید بساز و مدیرش باش؛ یک کد دعوت می‌گیری تا دوستانت را
            دعوت کنی.
          </p>
          {hasCompetitions ? (
            <Link className="btn btn-primary btn-block" href="/leagues/new">
              ساخت مسابقه
            </Link>
          ) : (
            <div className="alert alert-warning">
              هنوز هیچ تورنمنتی تعریف نشده؛ فعلاً نمی‌توانی مسابقه بسازی.
            </div>
          )}
        </div>
      </div>

      <div className="card mt">
        <h2 className="card-title">🏆 مسابقه‌های من</h2>
        {leagues.length > 0 ? (
          <div className="grid grid-2">
            {leagues.map((m) => (
              <Link key={m.slug} className="card tile" href={`/l/${m.slug}`}>
                <strong>{m.name}</strong>
                <div className="muted">{m.competition}</div>
                <div className="muted">{fa(m.member_count)} شرکت‌کننده</div>
                {m.is_owner && <span className="stage-badge">مدیر</span>}
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty">
            هنوز در هیچ مسابقه‌ای نیستی. با کد دعوت بپیوند یا یکی بساز.
          </div>
        )}
      </div>
    </>
  );
}
