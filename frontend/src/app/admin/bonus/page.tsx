import { redirect } from "next/navigation";

import { serverFetch } from "@/lib/server";
import type { MeT, AdminBonusLeagueT } from "@/lib/types";
import BonusAdminEditor from "@/components/BonusAdminEditor";

// Private page: enter members' tournament-wide bonus picks on their behalf.
// Only the admin may load it; the API behind it is admin-gated too.
export default async function AdminBonusPage() {
  const me = (await serverFetch("/me/")) as MeT;
  if (!me.is_admin) redirect("/dashboard");

  const leagues = (await serverFetch("/admin/bonus/leagues/")) as AdminBonusLeagueT[];

  return (
    <>
      <div className="page-head">
        <h1>ثبت پیش‌بینی‌های ویژه (به‌جای اعضا)</h1>
        <p>
          یک مسابقه و سپس یک عضو را انتخاب کن و پیش‌بینی‌های ویژهٔ او را وارد کن.
          این کار محدودیت مهلت را دور می‌زند، پس فقط برای ثبت پیش‌بینی‌هایی که
          اعضا پیش از مهلت داده‌اند استفاده کن.
        </p>
      </div>
      <BonusAdminEditor leagues={leagues} />
    </>
  );
}
