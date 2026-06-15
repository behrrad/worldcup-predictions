import type { Metadata } from "next";
import Script from "next/script";
import { Vazirmatn, Lalezar } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { faIR } from "@clerk/localizations";

import Header from "@/components/Header";
import "./globals.css";

const vazir = Vazirmatn({
  subsets: ["arabic", "latin"],
  variable: "--font-vazir",
  display: "swap",
});

const lalezar = Lalezar({
  weight: "400",
  subsets: ["arabic", "latin"],
  variable: "--font-lalezar",
  display: "swap",
});

export const metadata: Metadata = {
  title: "پیش‌بینی جام جهانی ۲۰۲۶",
  description: "رقابت پیش‌بینی نتایج جام جهانی ۲۰۲۶ با دوستان",
};

// The device default is handled purely in CSS (@media prefers-color-scheme),
// so this only needs to apply an explicit saved override before paint.
const themeInit = `(function(){try{var s=localStorage.getItem('wc-theme');if(s==='light'||s==='dark')document.documentElement.setAttribute('data-theme',s);}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // TEMP (recap demo only): render without Clerk so a public, auth-free demo
  // route can hydrate without a valid Clerk session. Guarded by an env flag —
  // normal runs (flag unset) are unaffected. Remove with the demo.
  if (process.env.NEXT_PUBLIC_DEMO_NO_CLERK === "1") {
    return (
      <html lang="fa" dir="rtl" className={`${vazir.variable} ${lalezar.variable}`} suppressHydrationWarning>
        <body>
          <main className="container main">{children}</main>
        </body>
      </html>
    );
  }
  return (
    <ClerkProvider
      localization={faIR}
      afterSignOutUrl="/"
      appearance={{ variables: { colorPrimary: "#ef3e42", borderRadius: "12px" } }}
    >
      <html
        lang="fa"
        dir="rtl"
        className={`${vazir.variable} ${lalezar.variable}`}
        suppressHydrationWarning
      >
        <body>
          {/* Apply a saved theme override before paint (the device default is
              handled in CSS). next/script avoids the React "script tag" warning. */}
          <Script
            id="theme-init"
            strategy="beforeInteractive"
            dangerouslySetInnerHTML={{ __html: themeInit }}
          />
          <Header />
          <main className="container main">{children}</main>
          <footer className="site-footer">
            <div className="container">
              پیش‌بینی جام جهانی ۲۰۲۶ · ساخته‌شده برای رقابت دوستانه{" "}
              <span className="heart">♥</span>
            </div>
          </footer>
        </body>
      </html>
    </ClerkProvider>
  );
}
