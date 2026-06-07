"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import type { CompetitionT } from "@/lib/types";

export default function CreateLeagueForm({
  competitions,
}: {
  competitions: CompetitionT[];
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [competitionId, setCompetitionId] = useState(
    competitions[0]?.id ?? "",
  );
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await getToken();
      const res = await apiFetch("/leagues/", token, {
        method: "POST",
        body: JSON.stringify({
          name,
          competition_id: competitionId,
          description,
        }),
      });
      router.push(`/l/${res.slug}`);
    } catch {
      setError("ساخت مسابقه ناموفق بود. ورودی‌ها را بررسی کنید.");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label>نام مسابقه</label>
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="مثلاً: رفقای جام جهانی ۲۰۲۶"
          required
        />
      </div>
      <div className="field">
        <label>تورنمنت</label>
        <select
          className="input"
          value={competitionId}
          onChange={(e) => setCompetitionId(Number(e.target.value))}
        >
          {competitions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>توضیحات (اختیاری)</label>
        <textarea
          className="input"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 14 }}>
          {error}
        </div>
      )}
      <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
        {loading ? "در حال ساخت…" : "ساخت مسابقه"}
      </button>
    </form>
  );
}
