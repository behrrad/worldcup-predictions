import { redirect } from "next/navigation";

import { serverFetch } from "@/lib/server";
import type { MeT, AdminMatchT } from "@/lib/types";
import ResultsEditor from "@/components/ResultsEditor";

// Private results-entry page. Only the admin (you) may load it — everyone else
// is bounced to the dashboard, and the API behind it is admin-gated too.
export default async function AdminResultsPage() {
  const me = (await serverFetch("/me/")) as MeT;
  if (!me.is_admin) redirect("/dashboard");

  const matches = (await serverFetch("/admin/matches/")) as AdminMatchT[];

  return (
    <>
      <div className="page-head">
        <h1>ورود نتایج بازی‌ها</h1>
        <p>نتیجهٔ هر بازی را وارد کن؛ امتیاز همه به‌صورت خودکار به‌روزرسانی می‌شود.</p>
      </div>
      <ResultsEditor matches={matches} />
    </>
  );
}
