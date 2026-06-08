"use client";

import Link from "next/link";
import { useUser, UserButton } from "@clerk/nextjs";

export default function Header() {
  const { isSignedIn, isLoaded } = useUser();

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-ball">⚽</span>
          <span className="brand-text">پیش‌بینی جام جهانی</span>
        </Link>
        <nav className="nav">
          <Link className="nav-link" href="/how-it-works">
            راهنما
          </Link>
          {!isLoaded ? null : isSignedIn ? (
            <>
              <Link className="nav-link" href="/dashboard">
                داشبورد
              </Link>
              <UserButton />
            </>
          ) : (
            <>
              <Link className="nav-link" href="/sign-in">
                ورود
              </Link>
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
