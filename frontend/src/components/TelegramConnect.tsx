"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { apiFetch } from "@/lib/api";
import type { TelegramStatus } from "@/lib/types";

// While waiting for the user to tap "Start" in the bot, poll the link status
// every few seconds — the GET endpoint drains pending bot updates, so the link
// completes here within a couple of seconds (no webhook needed).
const POLL_MS = 3000;
const POLL_MAX = 40; // give up after ~2 minutes of waiting

/**
 * Links the signed-in user's Telegram account so the reminder bot can DM them.
 * Renders nothing until the server reports a bot is configured (or the user is
 * already linked).
 *
 * - `variant="card"` (default, profile page): full controls — connect, plus a
 *   notify on/off toggle and disconnect once linked.
 * - `variant="banner"` (dashboard widget): a slim call-to-action shown only to
 *   people who haven't linked yet; disappears once connected.
 */
export default function TelegramConnect({
  variant = "card",
}: {
  variant?: "card" | "banner";
}) {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setWaiting(false);
  }, []);

  const refresh = useCallback(async (): Promise<TelegramStatus | null> => {
    const token = await getToken();
    const next = (await apiFetch("/me/telegram/", token)) as TelegramStatus;
    setStatus(next);
    return next;
  }, [getToken]);

  useEffect(() => {
    refresh().catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refresh]);

  function connect() {
    if (!status?.deep_link) return;
    window.open(status.deep_link, "_blank", "noopener,noreferrer");
    setError("");
    setWaiting(true);
    let attempts = 0;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const next = await refresh();
        if (next?.linked) stopPolling();
      } catch {
        /* keep polling */
      }
      if (attempts >= POLL_MAX) stopPolling();
    }, POLL_MS);
  }

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const token = await getToken();
      const next = (await apiFetch("/me/telegram/", token, {
        method: "PATCH",
        body: JSON.stringify(body),
      })) as TelegramStatus;
      setStatus(next);
    } catch {
      setError("ذخیرهٔ تنظیمات ناموفق بود. دوباره تلاش کن.");
    } finally {
      setBusy(false);
    }
  }

  // Hidden until the bot exists on the server (and the user isn't already linked).
  if (!status || (!status.configured && !status.linked)) return null;

  // Dashboard widget: a slim CTA that only nudges people who haven't linked yet.
  if (variant === "banner") {
    if (status.linked) return null;
    return (
      <div
        className="card"
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div>
          <h2 className="card-title" style={{ marginBottom: 6 }}>
            📲 یادآوری پیش‌بینی در تلگرام
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            تلگرامت را وصل کن تا پیش از هر بازی یادت بیندازیم پیش‌بینی کنی.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            className="btn btn-primary"
            onClick={connect}
            disabled={waiting || !status.deep_link}
          >
            {waiting ? "در انتظار اتصال…" : "اتصال به تلگرام"}
          </button>
          {waiting && (
            <span className="muted">در تلگرام دکمهٔ «Start / شروع» را بزن…</span>
          )}
        </div>
        {error && (
          <div className="alert alert-error" style={{ width: "100%" }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="card-title">📲 یادآوری در تلگرام</h2>

      {status.linked ? (
        <>
          <p className="muted">
            ✅ حساب تلگرام شما متصل است. یادآوری بازی‌هایی که پیش‌بینی نکرده‌ای و —
            در صورت فعال‌سازی — رویدادهای زندهٔ بازی‌ها را در تلگرام می‌فرستیم.
          </p>
          <div className="pred-actions">
            <button
              className={`btn ${status.notify ? "btn-outline" : "btn-pitch"}`}
              onClick={() => patch({ notify: !status.notify })}
              disabled={busy}
            >
              {status.notify ? "🔕 خاموش کردن یادآوری‌ها" : "🔔 روشن کردن یادآوری‌ها"}
            </button>
            <button
              className={`btn ${status.notify_matches ? "btn-outline" : "btn-pitch"}`}
              onClick={() => patch({ notify_matches: !status.notify_matches })}
              disabled={busy}
            >
              {status.notify_matches
                ? "⚽️ خاموش کردن اعلان رویدادهای بازی"
                : "⚽️ روشن کردن اعلان رویدادهای بازی"}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => patch({ unlink: true })}
              disabled={busy}
            >
              قطع اتصال
            </button>
          </div>
          {status.notify_matches && (
            <p className="muted" style={{ marginTop: 8, fontSize: "0.85em" }}>
              شروع، گل‌ها، پایان نیمه و نتیجهٔ نهایی هر بازی را همراه با پیش‌بینی
              خودت برایت می‌فرستیم.
            </p>
          )}
        </>
      ) : (
        <>
          <p className="muted">
            ربات تلگرام، بازی‌های امروز که هنوز پیش‌بینی نکرده‌ای و یک یادآوری
            نزدیک شروع هر بازی را برایت می‌فرستد.
          </p>
          <div className="pred-actions">
            <button
              className="btn btn-primary"
              onClick={connect}
              disabled={waiting || !status.deep_link}
            >
              {waiting ? "در انتظار اتصال…" : "اتصال به تلگرام"}
            </button>
            {waiting && (
              <span className="muted">
                در تلگرام روی دکمهٔ «Start / شروع» بزن…
              </span>
            )}
          </div>
        </>
      )}

      {error && (
        <div className="alert alert-error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
