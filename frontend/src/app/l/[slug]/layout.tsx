import { notFound } from "next/navigation";

import { serverFetch } from "@/lib/server";
import { fa } from "@/lib/format";
import LeagueTabs from "@/components/LeagueTabs";
import LiveScores from "@/components/LiveScores";
import SiteNotice from "@/components/SiteNotice";
import type { LeagueDetail } from "@/lib/types";

export default async function LeagueLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let league: LeagueDetail | null = null;
  try {
    league = (await serverFetch(`/leagues/${slug}/`)) as LeagueDetail;
  } catch {
    league = null;
  }
  if (!league) notFound();

  return (
    <>
      <div className="page-head">
        <h1>{league.name}</h1>
        <p>
          {league.competition.name} · {fa(league.member_count)} شرکت‌کننده
        </p>
      </div>
      <LeagueTabs slug={slug} />
      <SiteNotice />
      <LiveScores />
      {children}
    </>
  );
}
