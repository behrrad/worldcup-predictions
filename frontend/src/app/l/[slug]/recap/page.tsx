import { serverFetch } from "@/lib/server";
import RecapStory from "@/components/RecapStory";
import type { RecapResp } from "@/lib/types";

export default async function RecapPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const { slug } = await params;
  const { date } = await searchParams;
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  const recap = (await serverFetch(`/leagues/${slug}/recap/${qs}`)) as RecapResp;

  return <RecapStory slug={slug} recap={recap} />;
}
