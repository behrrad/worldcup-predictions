"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import type { LeagueDetail } from "@/lib/types";

/**
 * Owner-only, one-time prompt to opt this league into the 2× knockout boost
 * (quarter-finals onward). On accept, the backend raises the QF/SF/3rd/Final
 * multipliers to 2.0 and recomputes. Rendered only while the decision is PENDING;
 * once accepted it shows a small confirmation instead.
 */
export default function BoostPrompt({
  slug,
  initial,
}: {
  slug: string;
  initial: LeagueDetail["boost_decision"];
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [decision, setDecision] = useState(initial);
  const [loading, setLoading] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState("");

  async function decide(action: "accept" | "decline") {
    setLoading(action);
    setError("");
    try {
      const token = await getToken();
      const res = (await apiFetch(`/leagues/${slug}/`, token, {
        method: "PATCH",
        body: JSON.stringify({ boost_decision: action }),
      })) as LeagueDetail;
      setDecision(res.boost_decision);
      router.refresh();
    } catch {
      setError("ذخیرهٔ تصمیم ناموفق بود. دوباره تلاش کن.");
    } finally {
      setLoading(null);
    }
  }

  if (decision === "ACCEPTED") {
    return (
      <div className="card">
        <h2 className="card-title">⚡ ضریب ۲برابری فعال شد</h2>
        <p className="muted">
          از مرحلهٔ یک‌چهارم نهایی به بعد، امتیاز بازی‌های حذفی این مسابقه ۲ برابر
          محاسبه می‌شود.
        </p>
      </div>
    );
  }

  if (decision === "DECLINED") return null;

  return (
    <div className="card">
      <h2 className="card-title">⚡ ضریب امتیاز مراحل حذفی را ۲ برابر کنیم؟</h2>
      <p className="muted">
        از مرحلهٔ یک‌چهارم نهایی به بعد می‌توانی امتیاز بازی‌های حذفی را از ۱٫۵ برابر
        به <b>۲ برابر</b> افزایش بدهی تا پیش‌بینی بازی‌های بزرگِ پیش‌رو ارزش بیشتری
        داشته باشد. این تغییر فقط روی بازی‌های امتیازنگرفته اثر می‌گذارد.
      </p>
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          className="btn btn-pitch"
          onClick={() => decide("accept")}
          disabled={loading !== null}
        >
          {loading === "accept" ? "در حال ذخیره…" : "⚡ بله، ۲ برابر کن"}
        </button>
        <button
          className="btn btn-outline"
          onClick={() => decide("decline")}
          disabled={loading !== null}
        >
          {loading === "decline" ? "…" : "نه، همان ۱٫۵ بماند"}
        </button>
      </div>
    </div>
  );
}
