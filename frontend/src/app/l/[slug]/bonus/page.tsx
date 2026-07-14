import { serverFetch } from "@/lib/server";
import BonusForm from "@/components/BonusForm";
import BonusReveal from "@/components/BonusReveal";
import type { BonusResp, BonusAllResp } from "@/lib/types";

export default async function BonusPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [data, all] = await Promise.all([
    serverFetch(`/leagues/${slug}/bonus/`) as Promise<BonusResp>,
    serverFetch(`/leagues/${slug}/bonus/all/`) as Promise<BonusAllResp>,
  ]);

  return (
    <>
      <BonusForm slug={slug} data={data} />
      <BonusReveal data={all} />
    </>
  );
}
