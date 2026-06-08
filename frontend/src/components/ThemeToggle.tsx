"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "wc-theme";

// The effective theme is the explicit override on <html> if present, otherwise
// the device preference (which CSS applies when there is no data-theme attr).
function effectiveTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export default function ThemeToggle() {
  // Start as null so SSR markup and the first client render match.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(effectiveTheme());
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => {
      // Keep the icon in sync with the OS theme — but only while the user is
      // still following the device (no explicit override set on <html>).
      if (!document.documentElement.getAttribute("data-theme")) {
        setTheme(mq.matches ? "dark" : "light");
      }
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  function toggle() {
    // Read the live effective theme at click time, so a click before hydration
    // can't no-op or flip the wrong way.
    const next: Theme = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    setTheme(next);
  }

  const ready = theme !== null;
  const isDark = theme === "dark";

  // Until mounted, the effective theme is unknown, so don't expose a
  // (possibly wrong) pressed state — keep the button out of the a11y tree
  // and disabled, then enable it once the real theme is known.
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggle}
      disabled={!ready}
      tabIndex={ready ? undefined : -1}
      aria-hidden={ready ? undefined : true}
      aria-pressed={ready ? isDark : undefined}
      aria-label={ready ? (isDark ? "حالت روشن" : "حالت تیره") : "تغییر تم"}
      title={ready ? (isDark ? "حالت روشن" : "حالت تیره") : undefined}
    >
      {/* Render the icon for the theme you'd switch TO. Until mounted, show sun. */}
      {isDark ? (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="2" />
          <path
            d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M19 5l-1.4 1.4M6.4 17.6 5 19"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}
