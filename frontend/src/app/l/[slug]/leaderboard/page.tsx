import { serverFetch } from "@/lib/server";
import LeaderboardTable from "@/components/LeaderboardTable";
import type { LeaderboardResp } from "@/lib/types";

export default async function Leaderboard({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const board = (await serverFetch(
    `/leagues/${slug}/leaderboard/`,
  )) as LeaderboardResp;

  return <LeaderboardTable board={board} />;
}
