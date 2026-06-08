"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import { apiFetch, apiUpload } from "@/lib/api";
import Avatar from "@/components/Avatar";
import type { Profile, TeamT } from "@/lib/types";

export default function ProfileForm({
  initial,
  teams,
}: {
  initial: Profile;
  teams: TeamT[];
}) {
  const { getToken } = useAuth();
  const router = useRouter();

  const [displayName, setDisplayName] = useState(initial.display_name);
  const [bio, setBio] = useState(initial.bio);
  const [location, setLocation] = useState(initial.location);
  const [social, setSocial] = useState(initial.social_handle);
  const [favoriteTeam, setFavoriteTeam] = useState<string>(
    initial.favorite_team ? String(initial.favorite_team.id) : "",
  );
  const [avatar, setAvatar] = useState<string | null>(initial.avatar);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"ok" | "err" | "">("");

  // Teams arrive sorted by group; build optgroups for the picker.
  const groups = Array.from(new Set(teams.map((t) => t.group))).sort();

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const token = await getToken();
      await apiFetch("/me/", token, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: displayName,
          bio,
          location,
          social_handle: social,
          favorite_team_id: favoriteTeam === "" ? null : Number(favoriteTeam),
        }),
      });
      setStatus("ok");
      router.refresh();
    } catch {
      setStatus("err");
    } finally {
      setBusy(false);
    }
  }

  async function onAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setStatus("");
    try {
      const token = await getToken();
      const fd = new FormData();
      fd.append("avatar", file);
      const p = await apiUpload("/me/avatar/", token, fd);
      setAvatar(p.avatar);
      setStatus("ok");
      router.refresh();
    } catch {
      setStatus("err");
    } finally {
      setBusy(false);
      e.target.value = ""; // allow re-uploading the same file
    }
  }

  async function removeAvatar() {
    setBusy(true);
    setStatus("");
    try {
      const token = await getToken();
      const p = await apiFetch("/me/avatar/", token, { method: "DELETE" });
      setAvatar(p.avatar);
      router.refresh();
    } catch {
      setStatus("err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={saveProfile}>
      <div className="avatar-edit">
        <Avatar src={avatar} name={displayName || initial.public_name} size={88} />
        <div className="avatar-edit-actions">
          <label className="btn btn-outline btn-sm">
            تغییر عکس
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={onAvatarChange}
              disabled={busy}
              hidden
            />
          </label>
          {avatar && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={removeAvatar}
              disabled={busy}
            >
              حذف عکس
            </button>
          )}
          <span className="help">حداکثر ۵ مگابایت · JPEG/PNG/WebP/GIF</span>
        </div>
      </div>

      <div className="field">
        <label>نام نمایشی</label>
        <input
          className="input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={60}
          placeholder="مثلاً: علی"
        />
      </div>

      <div className="field">
        <label>تیم محبوب</label>
        <select
          className="input"
          value={favoriteTeam}
          onChange={(e) => setFavoriteTeam(e.target.value)}
        >
          <option value="">— انتخاب نشده —</option>
          {groups.map((g) => (
            <optgroup key={g} label={`گروه ${g}`}>
              {teams
                .filter((t) => t.group === g)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.flag} {t.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </div>

      <div className="field">
        <label>موقعیت مکانی</label>
        <input
          className="input"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          maxLength={80}
          placeholder="مثلاً: تهران، ایران"
        />
      </div>

      <div className="field">
        <label>نشانی شبکهٔ اجتماعی</label>
        <input
          className="input"
          value={social}
          onChange={(e) => setSocial(e.target.value)}
          maxLength={80}
          placeholder="مثلاً: @username"
        />
      </div>

      <div className="field">
        <label>دربارهٔ من</label>
        <textarea
          className="input"
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          maxLength={280}
          rows={3}
          placeholder="چند جمله دربارهٔ خودت…"
        />
        <div className="help">{280 - bio.length} نویسهٔ باقی‌مانده</div>
      </div>

      <div className="pred-actions">
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "در حال ذخیره…" : "ذخیرهٔ پروفایل"}
        </button>
        {status === "ok" && <span className="save-ok">ذخیره شد ✓</span>}
        {status === "err" && <span className="save-err">خطا در ذخیره</span>}
      </div>
    </form>
  );
}
