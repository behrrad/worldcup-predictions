"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { apiFetch } from "@/lib/api";
import { fmtDate, fmtTime, fa } from "@/lib/format";
import type { AdminMatchT } from "@/lib/types";

type Vals = Record<number, { home: string; away: string }>;
type SaveState = "idle" | "saving" | "saved" | "error";
type Filter = "pending" | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "بدون نتیجه" },
  { key: "all", label: "همه" },
];

function valsFor(m: AdminMatchT) {
  return {
    home: m.home_score != null ? String(m.home_score) : "",
    away: m.away_score != null ? String(m.away_score) : "",
  };
}

export default function ResultsEditor({
  matches: initial,
}: {
  matches: AdminMatchT[];
}) {
  const { getToken } = useAuth();
  const [matches, setMatches] = useState<AdminMatchT[]>(initial);
  const [vals, setVals] = useState<Vals>(() => {
    const init: Vals = {};
    for (const m of initial) init[m.id] = valsFor(m);
    return init;
  });
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});
  const [filter, setFilter] = useState<Filter>("pending");

  function setVal(id: number, side: "home" | "away", v: string) {
    setVals((s) => ({ ...s, [id]: { ...s[id], [side]: v } }));
    setSaveState((s) => ({ ...s, [id]: "idle" }));
  }

  async function post(id: number, body: Record<string, number | null>) {
    setSaveState((s) => ({ ...s, [id]: "saving" }));
    try {
      const token = await getToken();
      const updated = (await apiFetch(`/admin/matches/${id}/result/`, token, {
        method: "POST",
        body: JSON.stringify(body),
      })) as AdminMatchT;
      setMatches((ms) => ms.map((x) => (x.id === updated.id ? updated : x)));
      setVals((s) => ({ ...s, [updated.id]: valsFor(updated) }));
      setSaveState((s) => ({ ...s, [id]: "saved" }));
    } catch {
      setSaveState((s) => ({ ...s, [id]: "error" }));
    }
  }

  function save(m: AdminMatchT) {
    const v = vals[m.id];
    if (!v || v.home === "" || v.away === "") return;
    post(m.id, { home_score: Number(v.home), away_score: Number(v.away) });
  }

  function clearResult(m: AdminMatchT) {
    post(m.id, { home_score: null, away_score: null });
  }

  const visible = useMemo(
    () =>
      filter === "pending" ? matches.filter((m) => !m.is_finished) : matches,
    [matches, filter],
  );

  // Already chronologically ordered — group consecutive matches by calendar day.
  const groups = useMemo(() => {
    const out: { label: string; items: AdminMatchT[] }[] = [];
    const seen: Record<string, number> = {};
    for (const m of visible) {
      const label = fmtDate(m.kickoff);
      if (seen[label] === undefined) {
        seen[label] = out.length;
        out.push({ label, items: [] });
      }
      out[seen[label]].items.push(m);
    }
    return out;
  }, [visible]);

  const pendingCount = matches.filter((m) => !m.is_finished).length;
  const count = (k: Filter) => (k === "pending" ? pendingCount : matches.length);

  return (
    <>
      <div className="filter-chips">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`chip ${filter === f.key ? "active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            <span className="count">{fa(count(f.key))}</span>
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <div className="card">
          <div className="empty">بازی‌ای در این بخش نیست.</div>
        </div>
      ) : (
        groups.map((g) => (
          <div className="card" key={g.label}>
            <div className="day-header">{g.label}</div>
            {g.items.map((m) => {
              const state = saveState[m.id] ?? "idle";
              const ready = !!(m.home_team && m.away_team);
              const v = vals[m.id];
              return (
                <div className="pred-item" key={m.id}>
                  <div className="match-meta">
                    <span className="stage-badge">{m.stage_label}</span>
                    <span>
                      {fmtTime(m.kickoff)}{" "}
                      {m.is_finished ? (
                        <strong>· نتیجه ثبت‌شده</strong>
                      ) : (
                        <span className="muted">· بدون نتیجه</span>
                      )}
                    </span>
                  </div>
                  <div className="match">
                    <div className="team home">
                      <span>{m.home_team?.name ?? m.home_label ?? "؟"}</span>
                      <span className="flag">{m.home_team?.flag}</span>
                    </div>
                    <div className="score-box">
                      {ready ? (
                        <>
                          <input
                            className="score-input"
                            type="number"
                            min={0}
                            inputMode="numeric"
                            value={v.home}
                            onChange={(e) => setVal(m.id, "home", e.target.value)}
                          />
                          <span>:</span>
                          <input
                            className="score-input"
                            type="number"
                            min={0}
                            inputMode="numeric"
                            value={v.away}
                            onChange={(e) => setVal(m.id, "away", e.target.value)}
                          />
                        </>
                      ) : (
                        <span className="muted">تیم‌ها مشخص نشده</span>
                      )}
                    </div>
                    <div className="team away">
                      <span className="flag">{m.away_team?.flag}</span>
                      <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
                    </div>
                  </div>

                  {ready && (
                    <div className="pred-actions">
                      <span className="pred-action-right">
                        {state === "saved" && (
                          <span className="save-ok">✓ ذخیره شد</span>
                        )}
                        {state === "error" && <span className="save-err">خطا</span>}
                        {m.is_finished && (
                          <button
                            type="button"
                            className="btn btn-sm"
                            disabled={state === "saving"}
                            onClick={() => clearResult(m)}
                          >
                            پاک‌کردن
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-pitch btn-sm"
                          disabled={
                            state === "saving" || v.home === "" || v.away === ""
                          }
                          onClick={() => save(m)}
                        >
                          {state === "saving"
                            ? "در حال ذخیره…"
                            : m.is_finished
                              ? "به‌روزرسانی"
                              : "ثبت نتیجه"}
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
