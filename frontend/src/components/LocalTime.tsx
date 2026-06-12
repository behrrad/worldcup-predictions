"use client";

import { useSyncExternalStore } from "react";

import { fmtDateTime, SSR_TZ } from "@/lib/format";

const noopSubscribe = () => () => {};

/**
 * The viewer's IANA timezone. Returns SSR_TZ on the server and during
 * hydration so the client's first render matches the server HTML, then
 * re-renders once with the browser's real timezone.
 */
export function useTimeZone(): string {
  return useSyncExternalStore(
    noopSubscribe,
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    () => SSR_TZ,
  );
}

/**
 * Jalali date + time in the viewer's local timezone. A client-component leaf,
 * so Server Components can drop it in wherever they render a kickoff.
 */
export function LocalDateTime({ iso }: { iso: string }) {
  const tz = useTimeZone();
  return <>{fmtDateTime(iso, tz)}</>;
}
