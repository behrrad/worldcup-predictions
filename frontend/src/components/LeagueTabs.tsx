"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function LeagueTabs({ slug }: { slug: string }) {
  const pathname = usePathname();
  const base = `/l/${slug}`;
  const tabs = [
    { href: base, label: "نمای کلی" },
    { href: `${base}/predictions`, label: "ثبت پیش‌بینی" },
    { href: `${base}/all-predictions`, label: "پیش‌بینی همه" },
    { href: `${base}/leaderboard`, label: "جدول امتیازات" },
    { href: `${base}/members`, label: "اعضا" },
    { href: `${base}/matches`, label: "بازی‌ها و امتیاز من" },
    { href: `${base}/rules`, label: "قوانین" },
  ];

  return (
    <div className="section-tabs">
      {tabs.map((t) => {
        const active =
          t.href === base ? pathname === base : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`tab ${active ? "active" : ""}`}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
