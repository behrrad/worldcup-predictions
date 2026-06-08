"use client";

import Link from "next/link";
import { useUser, UserButton } from "@clerk/nextjs";

import ThemeToggle from "@/components/ThemeToggle";

export default function Header() {
  const { isSignedIn, isLoaded } = useUser();

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="23" height="23" viewBox="0 0 24 24" fill="none">
              <path d="M6 3h12v3a6 6 0 0 1-12 0V3Z" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
              <path d="M6 4H3.5v1.5A3.5 3.5 0 0 0 7 9M18 4h2.5v1.5A3.5 3.5 0 0 1 17 9" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
              <path d="M12 12v4M8.5 20h7M9.5 16h5l.5 4h-6l.5-4Z" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="brand-text">
            پیش‌بینی <b>جام جهانی</b>
            <span className="brand-sub">۲۰۲۶ · آمریکا · کانادا · مکزیک</span>
          </span>
        </Link>
        <nav className="nav">
          <Link className="nav-link" href="/how-it-works">
            راهنما
          </Link>
          {!isLoaded ? (
            <ThemeToggle />
          ) : isSignedIn ? (
            <>
              <Link className="nav-link" href="/dashboard">
                داشبورد
              </Link>
              <Link className="nav-link" href="/players">
                بازیکنان
              </Link>
              <Link className="nav-link" href="/profile">
                پروفایل من
              </Link>
              <ThemeToggle />
              <UserButton />
            </>
          ) : (
            <>
              <Link className="nav-link" href="/sign-in">
                ورود
              </Link>
              <ThemeToggle />
              <Link className="btn btn-primary btn-sm" href="/sign-up">
                ثبت‌نام
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
