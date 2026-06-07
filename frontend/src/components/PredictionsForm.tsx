"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { fmtDateTime, fa } from "@/lib/format";
import type { MatchT } from "@/lib/types";

type Vals = Record<number, { home: string; away: string }>;

export default function PredictionsForm({
  slug,
  matches,
}: {
  slug: string;
  matches: MatchT[];
}) {
  const { getToken } = useAuth();
  const router = useRouter();

  const [vals, setVals] = useState<Vals>(() => {
    const init: Vals = {};
    for (const m of matches) {
      init[m.id] = {
        home: m.my_prediction ? String(m.my_prediction.home) : "",
        away: m.my_prediction ? String(m.my_prediction.away) : "",
      };
    }
    return init;
  });
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  function setVal(id: number, side: "home" | "away", v: string) {
    setVals((s) => ({ ...s, [id]: { ...s[id], [side]: v } }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage("");
    const predictions = matches
      .filter((m) => m.can_predict)
      .map((m) => ({
        match_id: m.id,
        home: vals[m.id].home,
        away: vals[m.id].away,
      }))
      .filter((p) => p.home !== "" && p.away !== "");
    try {
      const token = await getToken();
      const res = await apiFetch(`/leagues/${slug}/predictions/`, token, {
        method: "POST",
        body: JSON.stringify({ predictions }),
      });
      setMessage(`${fa(res.saved)} پیش‌بینی ذخیره شد.`);
      router.refresh();
    } catch {
      setMessage("خطا در ذخیرهٔ پیش‌بینی‌ها.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {message && (
        <div className="alert alert-success" style={{ marginBottom: 14 }}>
          {message}
        </div>
      )}
      <div className="card">
        {matches.map((m) => (
          <div key={m.id}>
            <div className="match-meta">
              <span className="stage-badge">{m.stage_label}</span>
              <span>
                {fmtDateTime(m.kickoff)}{" "}
                {m.is_finished ? (
                  <strong>· پایان‌یافته</strong>
                ) : m.is_open ? (
                  <span className="lock-open">· باز</span>
                ) : (
                  <span className="lock-on">· بسته شد</span>
                )}
              </span>
            </div>
            <div className="match">
              <div className="team home">
                <span>{m.home_team?.name ?? "؟"}</span>
                <span className="flag">{m.home_team?.flag}</span>
              </div>
              <div className="score-box">
                {m.can_predict ? (
                  <>
                    <input
                      className="score-input"
                      type="number"
                      min={0}
                      inputMode="numeric"
                      value={vals[m.id].home}
                      onChange={(e) => setVal(m.id, "home", e.target.value)}
                    />
                    <span>:</span>
                    <input
                      className="score-input"
                      type="number"
                      min={0}
                      inputMode="numeric"
                      value={vals[m.id].away}
                      onChange={(e) => setVal(m.id, "away", e.target.value)}
                    />
                  </>
                ) : m.is_finished ? (
                  <span className="score-final">
                    {fa(m.home_score!)} : {fa(m.away_score!)}
                  </span>
                ) : m.my_prediction ? (
                  <span className="score-final">
                    {fa(m.my_prediction.home)} : {fa(m.my_prediction.away)}
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
              <div className="team away">
                <span className="flag">{m.away_team?.flag}</span>
                <span>{m.away_team?.name ?? "؟"}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
      <button className="btn btn-primary btn-block mt" type="submit" disabled={saving}>
        {saving ? "در حال ذخیره…" : "ذخیرهٔ پیش‌بینی‌ها"}
      </button>
    </form>
  );
}
