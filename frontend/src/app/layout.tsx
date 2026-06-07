import type { Metadata } from "next";
import { Vazirmatn } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { faIR } from "@clerk/localizations";

import Header from "@/components/Header";
import "./globals.css";

const vazir = Vazirmatn({
  subsets: ["arabic", "latin"],
  variable: "--font-vazir",
  display: "swap",
});

export const metadata: Metadata = {
  title: "پیش‌بینی جام جهانی",
  description: "رقابت پیش‌بینی نتایج جام جهانی با دوستان",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <ClerkProvider localization={faIR} afterSignOutUrl="/">
      <html lang="fa" dir="rtl" className={vazir.variable}>
        <body>
          <Header />
          <main className="container main">{children}</main>
          <footer className="site-footer">
            <div className="container">
              پیش‌بینی جام جهانی · ساخته‌شده برای رقابت دوستانه ⚽
            </div>
          </footer>
        </body>
      </html>
    </ClerkProvider>
  );
}
