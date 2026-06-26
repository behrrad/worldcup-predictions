import { serverFetch } from "@/lib/server";
import ProgressionChart from "@/components/ProgressionChart";
import type { ProgressionResp } from "@/lib/types";

export default async function ProgressionPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = (await serverFetch(
    `/leagues/${slug}/progression/`,
  )) as ProgressionResp;

  return <ProgressionChart data={data} />;
}
