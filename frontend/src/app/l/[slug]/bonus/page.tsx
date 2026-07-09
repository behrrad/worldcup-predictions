import { serverFetch } from "@/lib/server";
import BonusForm from "@/components/BonusForm";
import type { BonusResp } from "@/lib/types";

export default async function BonusPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = (await serverFetch(`/leagues/${slug}/bonus/`)) as BonusResp;

  return <BonusForm slug={slug} data={data} />;
}
