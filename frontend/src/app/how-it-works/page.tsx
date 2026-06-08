import Link from "next/link";

import { fa } from "@/lib/format";

export const metadata = {
  title: "چطور کار می‌کند؟ · پیش‌بینی جام جهانی",
};

export default function HowItWorks() {
  return (
    <>
      <div className="page-head">
        <h1>چطور کار می‌کند؟</h1>
        <p>
          هر چیزی که برای شروع رقابت پیش‌بینی جام جهانی با دوستانت لازم است بدانی.
        </p>
      </div>

      {/* What it is */}
      <div className="card how-section">
        <h2 className="card-title">⚽ این چیست؟</h2>
        <p>
          یک بازی دوستانه است: تو و دوستانت نتیجهٔ بازی‌های جام جهانی را پیش‌بینی
          می‌کنید و بر اساس دقت پیش‌بینی امتیاز می‌گیرید. هر کس امتیاز بیشتری جمع کند،
          بالاتر می‌ایستد. می‌توانی برای گروه‌های مختلف، مسابقه‌های جداگانه بسازی —
          مثلاً یکی با رفقای دانشگاه و یکی با همکارها — که هرکدام جدول و قوانین خودش
          را دارد.
        </p>
      </div>

      {/* How to join */}
      <div className="how-section">
        <h2 className="card-title">🚀 در سه قدم شروع کن</h2>
        <div className="steps">
          <div className="step">
            <div className="step-num">{fa(1)}</div>
            <h3>ثبت‌نام کن</h3>
            <p>
              با ایمیل یا حساب گوگل وارد شو. ساختن حساب چند ثانیه طول می‌کشد.
            </p>
          </div>
          <div className="step">
            <div className="step-num">{fa(2)}</div>
            <h3>به یک مسابقه بپیوند</h3>
            <p>
              کد دعوت دوستت را وارد کن تا عضو مسابقه شوی — یا خودت یک مسابقهٔ جدید
              بساز و کد دعوت را برای بقیه بفرست.
            </p>
          </div>
          <div className="step">
            <div className="step-num">{fa(3)}</div>
            <h3>پیش‌بینی کن</h3>
            <p>
              نتیجهٔ هر بازی را پیش از شروع آن ثبت کن. بعد از بازی، امتیازت خودکار
              محاسبه می‌شود.
            </p>
          </div>
        </div>
      </div>

      {/* Scoring */}
      <div className="card how-section">
        <h2 className="card-title">🏆 امتیازها چطور حساب می‌شوند؟</h2>
        <p className="muted">
          برای هر بازی، بالاترین موردی که با نتیجه بخواند به تو می‌رسد:
        </p>
        <table className="rules-table">
          <tbody>
            <tr>
              <td>
                نتیجهٔ دقیق <span className="muted">(مثلاً پیش‌بینی ۲-۱ و نتیجه ۲-۱)</span>
              </td>
              <td className="big">{fa(10)}</td>
            </tr>
            <tr>
              <td>
                برندهٔ درست + اختلاف گل درست{" "}
                <span className="muted">(مثلاً پیش‌بینی ۲-۱ و نتیجه ۳-۲)</span>
              </td>
              <td className="big">{fa(7)}</td>
            </tr>
            <tr>
              <td>فقط برندهٔ درست</td>
              <td className="big">{fa(5)}</td>
            </tr>
            <tr>
              <td>
                شرکت در پیش‌بینی <span className="muted">(ثبت پیش‌بینی، حتی اگر اشتباه باشد)</span>
              </td>
              <td className="big">{fa(2)}</td>
            </tr>
            <tr>
              <td>عدم ثبت پیش‌بینی</td>
              <td className="big">{fa(0)}</td>
            </tr>
          </tbody>
        </table>
        <p className="muted mt">
          بازی‌های <strong>مرحلهٔ حذفی</strong> ضریب <strong>×{fa(1.5)}</strong> دارند —
          پس یک پیش‌بینی دقیق در فینال {fa(10)}×{fa(1.5)} = {fa(15)} امتیاز می‌شود.
          این اعداد را مدیر هر مسابقه می‌تواند تغییر دهد.
        </p>
      </div>

      {/* Lock */}
      <div className="card how-section">
        <h2 className="card-title">⏰ مهلت ثبت پیش‌بینی</h2>
        <p>
          پیش‌بینی هر بازی <strong>{fa(30)} دقیقه</strong> پیش از شروع آن بسته می‌شود.
          تا آن لحظه می‌توانی پیش‌بینی‌ات را تغییر دهی؛ بعد از آن قفل می‌شود و
          پیش‌بینی دیگران هم تازه آن وقت برای همه قابل دیدن می‌شود — پس کسی نمی‌تواند
          از روی دست بقیه بنویسد.
        </p>
      </div>

      <div className="card center how-section">
        <h2 className="card-title" style={{ justifyContent: "center" }}>
          آماده‌ای؟
        </h2>
        <div className="hero-actions">
          <Link className="btn btn-primary" href="/sign-up">
            ثبت‌نام و شروع
          </Link>
          <Link className="btn btn-outline" href="/sign-in">
            ورود
          </Link>
        </div>
      </div>
    </>
  );
}
