const TZ = "Asia/Tehran";

/** Persian (Jalali) date + time, e.g. «۲۱ خرداد ۱۴۰۵، ۲۱:۳۰». */
export function fmtDateTime(iso: string): string {
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: TZ,
  }).format(new Date(iso));
}

/** Persian (Jalali) full date with weekday, e.g. «پنجشنبه ۲۱ خرداد ۱۴۰۵». */
export function fmtDate(iso: string): string {
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "full",
    timeZone: TZ,
  }).format(new Date(iso));
}

export function fmtTime(iso: string): string {
  return new Intl.DateTimeFormat("fa-IR", {
    timeStyle: "short",
    timeZone: TZ,
  }).format(new Date(iso));
}

/** Convert a number to Persian digits. */
export function fa(n: number | string): string {
  return String(n).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}
