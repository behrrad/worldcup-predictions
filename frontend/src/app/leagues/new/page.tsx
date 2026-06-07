import { serverFetch } from "@/lib/server";
import CreateLeagueForm from "@/components/CreateLeagueForm";
import type { CompetitionT } from "@/lib/types";

export default async function NewLeague() {
  const competitions = (await serverFetch("/competitions/")) as CompetitionT[];

  return (
    <>
      <div className="page-head">
        <h1>ساخت مسابقهٔ جدید</h1>
        <p>یک لیگ پیش‌بینی برای گروه دوستانت بساز</p>
      </div>
      <div className="card" style={{ maxWidth: 560 }}>
        <CreateLeagueForm competitions={competitions} />
      </div>
    </>
  );
}
