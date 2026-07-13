import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { fa } from "@/lib/format";

export default async function Home() {
  const { userId } = await auth();
  if (userId) redirect("/dashboard");

  return (
    <>
      <section className="hero">
        <span className="kicker">
          🇺🇸 🇨🇦 🇲🇽 میزبانی آمریکا · کانادا · مکزیک
        </span>
        <h1>
          <span className="accent">جام جهانی ۲۰۲۶</span> را{" "}
          <span className="accent2">پیش‌بینی</span> کن
        </h1>
        <p>
          با دوستانت نتیجهٔ بازی‌های جام جهانی را پیش‌بینی کن، امتیاز جمع کن و
          صدرنشین جدول شو.
        </p>
        <div className="hero-actions">
          <Link className="btn btn-primary" href="/sign-up">
            شروع کن
          </Link>
          <Link className="btn btn-outline" href="/sign-in">
            ورود
          </Link>
          <Link className="btn btn-outline" href="/scoreboard">
            جدول کل بازیکنان
          </Link>
        </div>
      </section>

      <div className="grid grid-3">
        <div className="card stat">
          <div className="num">{fa(10)}</div>
          <div className="label">امتیاز نتیجهٔ دقیق</div>
        </div>
        <div className="card stat">
          <div className="num">{fa(7)}</div>
          <div className="label">برندهٔ درست + اختلاف گل</div>
        </div>
        <div className="card stat">
          <div className="num">{fa(5)}</div>
          <div className="label">فقط برندهٔ درست</div>
        </div>
      </div>

      <div className="card mt">
        <h2 className="card-title">چطور کار می‌کند؟</h2>
        <ol>
          <li>
            ثبت‌نام کن و با کد دعوت به مسابقهٔ دوستانت بپیوند — یا خودت یک مسابقه
            بساز و مدیرش باش.
          </li>
          <li>
            نتیجهٔ هر بازی را تا <strong>لحظهٔ شروع</strong> آن
            پیش‌بینی کن.
          </li>
          <li>بعد از هر بازی، امتیازها خودکار حساب می‌شوند و جدول به‌روز می‌شود.</li>
          <li>
            مراحل حذفی ضریب <strong>×{fa(1.5)}</strong> دارند — هیجان دوبرابر!
          </li>
        </ol>
        <Link className="btn btn-outline mt" href="/how-it-works">
          راهنمای کامل و قوانین امتیازدهی
        </Link>
      </div>
    </>
  );
}
