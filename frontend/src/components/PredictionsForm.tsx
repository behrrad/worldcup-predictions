"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { apiFetch } from "@/lib/api";
import { fmtDate, fmtTime, fa } from "@/lib/format";
import type { MatchT } from "@/lib/types";

type Vals = Record<number, { home: string; away: string }>;
type SaveState = "idle" | "saving" | "saved" | "error";
type Filter = "open" | "group" | "knockout" | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "open", label: "باز برای پیش‌بینی" },
  { key: "group", label: "مرحلهٔ گروهی" },
  { key: "knockout", label: "مراحل حذفی" },
  { key: "all", label: "همه" },
];

export default function PredictionsForm({
  slug,
  matches,
}: {
  slug: string;
  matches: MatchT[];
}) {
  const { getToken } = useAuth();

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
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});
  const [predicted, setPredicted] = useState<Set<number>>(
    () => new Set(matches.filter((m) => m.my_prediction).map((m) => m.id)),
  );
  const [filter, setFilter] = useState<Filter>("open");

  const openCount = matches.filter((m) => m.can_predict).length;

  function counts(key: Filter) {
    if (key === "open") return matches.filter((m) => m.can_predict).length;
    if (key === "group") return matches.filter((m) => m.stage === "GROUP").length;
    if (key === "knockout") return matches.filter((m) => m.stage !== "GROUP").length;
    return matches.length;
  }

  function setVal(id: number, side: "home" | "away", v: string) {
    setVals((s) => ({ ...s, [id]: { ...s[id], [side]: v } }));
    setSaveState((s) => ({ ...s, [id]: "idle" }));
  }

  async function saveMatch(m: MatchT) {
    const v = vals[m.id];
    if (!v || v.home === "" || v.away === "") return;
    setSaveState((s) => ({ ...s, [m.id]: "saving" }));
    try {
      const token = await getToken();
      const res = await apiFetch(`/leagues/${slug}/predictions/`, token, {
        method: "POST",
        body: JSON.stringify({
          predictions: [{ match_id: m.id, home: v.home, away: v.away }],
        }),
      });
      if (res.saved >= 1) {
        setSaveState((s) => ({ ...s, [m.id]: "saved" }));
        setPredicted((p) => new Set(p).add(m.id));
      } else {
        setSaveState((s) => ({ ...s, [m.id]: "error" }));
      }
    } catch {
      setSaveState((s) => ({ ...s, [m.id]: "error" }));
    }
  }

  const filtered = useMemo(() => {
    if (filter === "open") return matches.filter((m) => m.can_predict);
    if (filter === "group") return matches.filter((m) => m.stage === "GROUP");
    if (filter === "knockout") return matches.filter((m) => m.stage !== "GROUP");
    return matches;
  }, [matches, filter]);

  // Group consecutive (already chronologically sorted) matches by calendar day.
  const groups = useMemo(() => {
    const out: { label: string; items: MatchT[] }[] = [];
    const seen: Record<string, number> = {};
    for (const m of filtered) {
      const label = fmtDate(m.kickoff);
      if (seen[label] === undefined) {
        seen[label] = out.length;
        out.push({ label, items: [] });
      }
      out[seen[label]].items.push(m);
    }
    return out;
  }, [filtered]);

  const hasPred = (m: MatchT) => !!m.my_prediction || predicted.has(m.id);

  return (
    <>
      <div className="pred-summary">
        <div className="metric">
          <b>{fa(openCount)}</b>
          <span>بازی باز برای پیش‌بینی</span>
        </div>
        <div className="metric">
          <b>{fa(predicted.size)}</b>
          <span>پیش‌بینی ثبت‌شده</span>
        </div>
        <div className="metric">
          <b>{fa(matches.length)}</b>
          <span>کل بازی‌ها</span>
        </div>
      </div>

      <div className="filter-chips">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`chip ${filter === f.key ? "active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            <span className="count">{fa(counts(f.key))}</span>
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <div className="card">
          <div className="empty">
            {filter === "open"
              ? "فعلاً بازی‌ای برای پیش‌بینی باز نیست. برای دیدن همهٔ بازی‌ها از فیلتر «همه» استفاده کن."
              : "بازی‌ای در این بخش نیست."}
          </div>
        </div>
      ) : (
        groups.map((g) => (
          <div className="card" key={g.label}>
            <div className="day-header">{g.label}</div>
            {g.items.map((m) => {
              const state = saveState[m.id] ?? "idle";
              return (
                <div className="pred-item" key={m.id}>
                  <div className="match-meta">
                    <span className="stage-badge">{m.stage_label}</span>
                    <span>
                      {fmtTime(m.kickoff)}{" "}
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
                      <span>{m.home_team?.name ?? m.home_label ?? "؟"}</span>
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
                      <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
                    </div>
                  </div>

                  {m.can_predict && (
                    <div className="pred-actions">
                      <span>
                        {hasPred(m) ? (
                          <span className="badge-predicted">✓ پیش‌بینی ثبت شده</span>
                        ) : (
                          <span className="muted">هنوز پیش‌بینی نکرده‌ای</span>
                        )}
                      </span>
                      <span className="pred-action-right">
                        {state === "saved" && <span className="save-ok">✓ ذخیره شد</span>}
                        {state === "error" && <span className="save-err">ذخیره نشد</span>}
                        <button
                          type="button"
                          className="btn btn-pitch btn-sm"
                          disabled={
                            state === "saving" ||
                            vals[m.id].home === "" ||
                            vals[m.id].away === ""
                          }
                          onClick={() => saveMatch(m)}
                        >
                          {state === "saving"
                            ? "در حال ذخیره…"
                            : hasPred(m)
                              ? "به‌روزرسانی"
                              : "ثبت پیش‌بینی"}
                        </button>
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))
      )}
    </>
  );
}
