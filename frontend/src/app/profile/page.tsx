import { serverFetch } from "@/lib/server";
import ProfileForm from "@/components/ProfileForm";
import TelegramConnect from "@/components/TelegramConnect";
import type { Profile, TeamT } from "@/lib/types";

export default async function ProfilePage() {
  const [profile, teams] = await Promise.all([
    serverFetch("/me/") as Promise<Profile>,
    serverFetch("/teams/") as Promise<TeamT[]>,
  ]);

  return (
    <>
      <div className="page-head">
        <h1>پروفایل من</h1>
        <p>این اطلاعات برای بقیهٔ بازیکنان نمایش داده می‌شود.</p>
      </div>
      <div className="card">
        <ProfileForm initial={profile} teams={teams} />
      </div>
      <TelegramConnect />
    </>
  );
}
