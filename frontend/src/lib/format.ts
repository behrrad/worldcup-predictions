/**
 * Timezone used on the server and during hydration, where the viewer's real
 * timezone is unknown. Client code passes `useTimeZone()` (components/LocalTime)
 * to render in the viewer's local timezone instead.
 */
export const SSR_TZ = "Asia/Tehran";

/** Persian (Jalali) date + time, e.g. «۲۱ خرداد ۱۴۰۵، ۲۱:۳۰». */
export function fmtDateTime(iso: string, timeZone: string = SSR_TZ): string {
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(iso));
}

/** Persian (Jalali) full date with weekday, e.g. «پنجشنبه ۲۱ خرداد ۱۴۰۵». */
export function fmtDate(iso: string, timeZone: string = SSR_TZ): string {
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "full",
    timeZone,
  }).format(new Date(iso));
}

export function fmtTime(iso: string, timeZone: string = SSR_TZ): string {
  return new Intl.DateTimeFormat("fa-IR", {
    timeStyle: "short",
    timeZone,
  }).format(new Date(iso));
}

/** Convert a number to Persian digits. */
export function fa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

/**
 * A matchday label (full Jalali date) from a `YYYY-MM-DD` string. A matchday is
 * a calendar day in the league's timezone (SSR_TZ), so it's always rendered
 * there — noon Tehran keeps the date stable whatever the viewer's timezone is.
 */
export function fmtJalaliDay(ymd: string): string {
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "full",
    timeZone: SSR_TZ,
  }).format(new Date(`${ymd}T12:00:00+03:30`));
}
