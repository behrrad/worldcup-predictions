import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import type { LeagueDetail } from "@/lib/types";

export default async function Rules({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const league = (await serverFetch(`/leagues/${slug}/`)) as LeagueDetail;
  const s = league.scoring;
  const finalMult = s.stage_multipliers.find((m) => m.stage === "F");

  return (
    <>
      <div className="card">
        <h2 className="card-title">📋 امتیاز هر پیش‌بینی</h2>
        <p className="muted">
          برای هر بازی، بالاترین حالتی که با نتیجه جور دربیاید به تو می‌رسد:
        </p>
        <table className="rules-table">
          <tbody>
            <tr>
              <td>
                نتیجهٔ دقیق{" "}
                <span className="muted">(مثلاً پیش‌بینی ۲-۱ و نتیجه ۲-۱)</span>
              </td>
              <td className="big">{fa(s.points_exact)}</td>
            </tr>
            <tr>
              <td>
                برندهٔ درست + اختلاف گل درست{" "}
                <span className="muted">(مثلاً پیش‌بینی ۲-۱ و نتیجه ۳-۲)</span>
              </td>
              <td className="big">{fa(s.points_correct_diff)}</td>
            </tr>
            <tr>
              <td>
                فقط برندهٔ درست{" "}
                <span className="muted">(برنده درست، اختلاف اشتباه)</span>
              </td>
              <td className="big">{fa(s.points_correct_winner)}</td>
            </tr>
            <tr>
              <td>
                ثبت پیش‌بینی <span className="muted">(حتی اگر اشتباه باشد)</span>
              </td>
              <td className="big">{fa(s.points_participation)}</td>
            </tr>
            <tr>
              <td>عدم ثبت پیش‌بینی</td>
              <td className="big">{fa(0)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="card-title">⚡ ضریب مراحل</h2>
        <p className="muted">امتیاز پایهٔ هر بازی در ضریب مرحلهٔ آن ضرب می‌شود:</p>
        <table className="rules-table">
          <tbody>
            {s.stage_multipliers.map((m) => (
              <tr key={m.stage}>
                <td>{m.label}</td>
                <td className="big">×{fa(m.multiplier)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {finalMult && (
          <p className="muted mt">
            مثال: نتیجهٔ دقیق در فینال با ضریب ×{fa(finalMult.multiplier)} می‌شود{" "}
            {fa(s.points_exact)}×{fa(finalMult.multiplier)} ={" "}
            {fa(s.points_exact * finalMult.multiplier)}.
          </p>
        )}
      </div>

      <div className="card">
        <h2 className="card-title">⏰ زمان بسته‌شدن پیش‌بینی</h2>
        <p>
          پیش‌بینی هر بازی <strong>{fa(s.lock_minutes)} دقیقه</strong> پیش از شروع
          آن بسته می‌شود و دیگر قابل تغییر نیست.{" "}
          {league.reveal_predictions
            ? "پیش‌بینی دیگران هم تا آن لحظه برای بقیه قابل دیدن نیست و بعد از آن نمایش داده می‌شود."
            : "مدیر این مسابقه نمایش پیش‌بینی دیگران را خاموش کرده است؛ پیش‌بینی هر کس فقط برای خودش قابل دیدن است."}
        </p>
      </div>
    </>
  );
}
