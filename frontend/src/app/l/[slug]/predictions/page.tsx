import { serverFetch } from "@/lib/server";
import PredictionsForm from "@/components/PredictionsForm";
import type { MatchT } from "@/lib/types";

export default async function PredictionsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const matches = (await serverFetch(`/leagues/${slug}/matches/`)) as MatchT[];

  return <PredictionsForm slug={slug} matches={matches} />;
}
