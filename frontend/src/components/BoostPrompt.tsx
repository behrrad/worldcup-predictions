"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { fa } from "@/lib/format";
import type { LeagueDetail } from "@/lib/types";

// Keep in sync with consts.BOOST_MIN_MULTIPLIER / BOOST_MAX_MULTIPLIER (backend
// re-validates, so this is just for a friendly client-side message).
const MIN = 1;
const MAX = 5;

/**
 * Owner-only control for the QF-onward knockout multiplier (quarter-finals and
 * after). While the decision is PENDING it shows the announcement prompt (accept
 * 2× / decline). In every state the owner can also type a custom multiplier and
 * save it — the backend sets QF/SF/3rd/Final together and recomputes scores.
 */
export default function BoostPrompt({
  slug,
  decision,
  multiplier,
}: {
  slug: string;
  decision: LeagueDetail["boost_decision"];
  multiplier: number;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [state, setState] = useState(decision);
  const [current, setCurrent] = useState(multiplier);
  const [value, setValue] = useState(String(multiplier));
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function patch(body: object, tag: string) {
    setLoading(tag);
    setError("");
    try {
      const token = await getToken();
      const res = (await apiFetch(`/leagues/${slug}/`, token, {
        method: "PATCH",
        body: JSON.stringify(body),
      })) as LeagueDetail;
      setState(res.boost_decision);
      setCurrent(res.boost_multiplier);
      setValue(String(res.boost_multiplier));
      router.refresh();
    } catch {
      setError("ذخیره ناموفق بود. دوباره تلاش کن.");
    } finally {
      setLoading(null);
    }
  }

  function saveCustom() {
    const n = Number(value);
    if (!Number.isFinite(n) || n < MIN || n > MAX) {
      setError(`ضریب باید عددی بین ${fa(MIN)} تا ${fa(MAX)} باشد.`);
      return;
    }
    patch({ boost_multiplier: n }, "save");
  }

  const editor = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <label className="muted" htmlFor="boost-input">
        ضریب دلخواه (از یک‌چهارم نهایی):
      </label>
      <input
        id="boost-input"
        type="number"
        min={MIN}
        max={MAX}
        step={0.1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={{ width: 90 }}
      />
      <button
        className="btn btn-outline"
        onClick={saveCustom}
        disabled={loading !== null}
      >
        {loading === "save" ? "در حال ذخیره…" : "ذخیره"}
      </button>
    </div>
  );

  return (
    <div className="card">
      <h2 className="card-title">⚡ ضریب امتیاز مراحل حذفی</h2>

      {state === "PENDING" ? (
        <p className="muted">
          از مرحلهٔ یک‌چهارم نهایی به بعد می‌توانی امتیاز بازی‌های حذفی را از ۱٫۵
          برابر به <b>۲ برابر</b> افزایش بدهی تا پیش‌بینی بازی‌های بزرگِ پیش‌رو ارزش
          بیشتری داشته باشد. این تغییر فقط روی بازی‌های امتیازنگرفته اثر می‌گذارد.
        </p>
      ) : (
        <p className="muted">
          ضریب فعلی بازی‌های حذفی (از یک‌چهارم نهایی): <b>{fa(current)}×</b>
          {state === "ACCEPTED" ? " — فعال است." : " — پیش‌فرض."} هر وقت خواستی
          می‌توانی آن را تغییر بدهی.
        </p>
      )}

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      {state === "PENDING" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            className="btn btn-pitch"
            onClick={() => patch({ boost_decision: "accept" }, "accept")}
            disabled={loading !== null}
          >
            {loading === "accept" ? "در حال ذخیره…" : "⚡ بله، ۲ برابر کن"}
          </button>
          <button
            className="btn btn-outline"
            onClick={() => patch({ boost_decision: "decline" }, "decline")}
            disabled={loading !== null}
          >
            {loading === "decline" ? "…" : "نه، همان ۱٫۵ بماند"}
          </button>
        </div>
      )}

      {editor}
    </div>
  );
}
