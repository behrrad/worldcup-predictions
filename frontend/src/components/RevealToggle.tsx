"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import type { LeagueDetail } from "@/lib/types";

/**
 * Owner-only switch that controls whether other members' predictions are shown
 * once a match locks. Off => everyone's picks stay private for good.
 */
export default function RevealToggle({
  slug,
  initial,
}: {
  slug: string;
  initial: boolean;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [on, setOn] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    setLoading(true);
    setError("");
    try {
      const token = await getToken();
      const res = (await apiFetch(`/leagues/${slug}/`, token, {
        method: "PATCH",
        body: JSON.stringify({ reveal_predictions: !on }),
      })) as LeagueDetail;
      setOn(res.reveal_predictions);
      router.refresh(); // re-render the match/rules pages with the new setting
    } catch {
      setError("ذخیرهٔ تنظیمات ناموفق بود. دوباره تلاش کن.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2 className="card-title">👁️ نمایش پیش‌بینی دیگران</h2>
      <p className="muted">
        {on
          ? "پس از بسته‌شدن هر بازی (هنگام شروع آن)، پیش‌بینی بقیه برای همهٔ اعضا نمایش داده می‌شود."
          : "پیش‌بینی اعضا همیشه خصوصی می‌ماند و برای دیگران نمایش داده نمی‌شود."}
      </p>
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      <button
        className={`btn ${on ? "btn-outline" : "btn-pitch"}`}
        onClick={toggle}
        disabled={loading}
      >
        {loading
          ? "در حال ذخیره…"
          : on
            ? "🔒 پنهان کردن پیش‌بینی‌ها از دیگران"
            : "👁️ نمایش پیش‌بینی‌ها به همه"}
      </button>
    </div>
  );
}
