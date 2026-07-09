"use client";

import { useEffect, useState } from "react";

// Bump the id (and the copy) to re-announce something new later; dismissals are
// stored per-id in localStorage, so a fresh id shows the banner to everyone again.
const NOTICE_ID = "notice-2026-qf-2x";
const STORAGE_KEY = `dismissed:${NOTICE_ID}`;

/**
 * A dismissible, RTL announcement banner shown across the app. Renders nothing
 * until mounted (so the server/client markup matches) and stays hidden once the
 * viewer dismisses this notice id.
 */
export default function SiteNotice() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(localStorage.getItem(STORAGE_KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);

  if (!show) return null;

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setShow(false);
  }

  return (
    <div
      className="alert alert-info"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        marginBottom: 16,
      }}
    >
      <span style={{ fontSize: "1.4rem" }}>📣</span>
      <span style={{ flex: 1, lineHeight: 1.6 }}>
        از مرحلهٔ یک‌چهارم نهایی به بعد، امتیاز بازی‌های حذفی <b>۲ برابر</b> می‌شود
        (به‌جای ۱٫۵ برابر). مدیرهای مسابقه‌ها می‌توانند این تغییر را در صفحهٔ مسابقهٔ
        خود تأیید کنند.
      </span>
      <button
        onClick={dismiss}
        aria-label="بستن"
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "1.1rem",
          color: "inherit",
          lineHeight: 1,
        }}
      >
        ✕
      </button>
    </div>
  );
}
