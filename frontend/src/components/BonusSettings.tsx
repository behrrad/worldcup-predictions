"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useTimeZone } from "@/components/LocalTime";
import type { LeagueDetail } from "@/lib/types";

/** ISO instant -> a `datetime-local` input value in the viewer's local time. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * Owner-only switch for the tournament-wide bonus predictions. Setting a
 * deadline turns the feature on (and is the moment picks lock); clearing it
 * turns the feature off for this league.
 */
export default function BonusSettings({
  slug,
  initial,
}: {
  slug: string;
  initial: string | null;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const tz = useTimeZone();
  const [lockAt, setLockAt] = useState<string | null>(initial);
  const [value, setValue] = useState<string>(initial ? toLocalInput(initial) : "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const on = lockAt !== null;

  async function patch(body: Record<string, unknown>) {
    setLoading(true);
    setError("");
    try {
      const token = await getToken();
      const res = (await apiFetch(`/leagues/${slug}/`, token, {
        method: "PATCH",
        body: JSON.stringify(body),
      })) as LeagueDetail;
      setLockAt(res.scoring.bonus_lock_at);
      setValue(res.scoring.bonus_lock_at ? toLocalInput(res.scoring.bonus_lock_at) : "");
      router.refresh(); // re-render the bonus/rules pages with the new setting
    } catch {
      setError("ذخیرهٔ تنظیمات ناموفق بود. دوباره تلاش کن.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2 className="card-title">🏆 پیش‌بینی‌های ویژه (قهرمانی)</h2>
      <p className="muted">
        با فعال‌کردن این بخش، اعضا می‌توانند تا مهلت تعیین‌شده قهرمان جام، آقای گل،
        بهترین بازیکن و «قهرمان مسابقهٔ ما» را پیش‌بینی کنند. پس از مهلت،
        پیش‌بینی‌ها قفل می‌شود.
      </p>
      {on ? (
        <p className="badge-predicted">
          ✓ فعال — مهلت: {fmtDateTime(lockAt!, tz)}
        </p>
      ) : (
        <p className="lock-on">در حال حاضر خاموش است.</p>
      )}
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      <div className="field">
        <label>مهلت ثبت پیش‌بینی‌های ویژه</label>
        <input
          className="input"
          type="datetime-local"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <div className="help">پیشنهاد: کمی پیش از شروع مرحلهٔ بعدی مسابقات.</div>
      </div>
      <button
        className="btn btn-pitch"
        onClick={() => value && patch({ bonus_lock_at: new Date(value).toISOString() })}
        disabled={loading || !value}
      >
        {loading ? "در حال ذخیره…" : on ? "به‌روزرسانی مهلت" : "فعال‌سازی"}
      </button>
      {on && (
        <button
          className="btn btn-outline"
          onClick={() => patch({ bonus_lock_at: null })}
          disabled={loading}
          style={{ marginInlineStart: 8 }}
        >
          خاموش کردن
        </button>
      )}
    </div>
  );
}
