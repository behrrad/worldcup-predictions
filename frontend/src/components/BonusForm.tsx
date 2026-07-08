"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { apiFetch } from "@/lib/api";
import { fmtDateTime, fa } from "@/lib/format";
import { useTimeZone } from "@/components/LocalTime";
import type { BonusResp, BonusQuestionT } from "@/lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";

export default function BonusForm({
  slug,
  data,
}: {
  slug: string;
  data: BonusResp;
}) {
  const { getToken } = useAuth();
  const tz = useTimeZone();

  const [picks, setPicks] = useState<Record<string, number | "">>(() => {
    const init: Record<string, number | ""> = {};
    for (const q of data.questions) init[q.kind] = q.my_pick ?? "";
    return init;
  });
  const [saveState, setSaveState] = useState<Record<string, SaveState>>({});

  const editable = data.enabled && data.is_open;

  // id -> label lookups for each answer type, so we can render a pick / the
  // correct answer as a name (not just an id).
  const teamLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const t of data.teams)
      m.set(t.id, `${t.flag ? t.flag + " " : ""}${t.name}`);
    return m;
  }, [data.teams]);
  const playerLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of data.players)
      m.set(p.id, p.team ? `${p.name} (${p.team.name})` : p.name);
    return m;
  }, [data.players]);
  const memberLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const mem of data.members)
      m.set(mem.id, mem.is_me ? `${mem.name} (خودت)` : mem.name);
    return m;
  }, [data.members]);

  function labels(q: BonusQuestionT): Map<number, string> {
    if (q.answer_type === "team") return teamLabel;
    if (q.answer_type === "player") return playerLabel;
    return memberLabel;
  }

  function options(q: BonusQuestionT): { id: number; label: string }[] {
    return [...labels(q).entries()].map(([id, label]) => ({ id, label }));
  }

  function nameFor(q: BonusQuestionT, id: number | null): string {
    if (id == null) return "—";
    return labels(q).get(id) ?? "—";
  }

  async function save(kind: string, value: number | "") {
    setSaveState((s) => ({ ...s, [kind]: "saving" }));
    try {
      const token = await getToken();
      const res = await apiFetch(`/leagues/${slug}/bonus/`, token, {
        method: "POST",
        body: JSON.stringify({
          picks: [{ kind, value: value === "" ? null : value }],
        }),
      });
      setSaveState((s) => ({
        ...s,
        [kind]: res.saved >= 1 ? "saved" : "error",
      }));
    } catch {
      setSaveState((s) => ({ ...s, [kind]: "error" }));
    }
  }

  function onChange(kind: string, raw: string) {
    const value = raw === "" ? "" : Number(raw);
    setPicks((p) => ({ ...p, [kind]: value }));
    save(kind, value);
  }

  if (!data.enabled) {
    return (
      <div className="card">
        <div className="empty">
          پیش‌بینی‌های ویژه برای این مسابقه فعال نشده است. مدیر مسابقه می‌تواند از
          پنل مدیریت آن را روشن کند.
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card">
        <h2 className="card-title">🏆 پیش‌بینی‌های ویژه</h2>
        <p className="muted">
          جدا از پیش‌بینی نتیجهٔ بازی‌ها، اینجا چند سؤال دربارهٔ کل تورنمنت هست.
          هر جواب درست، امتیاز کاملش را می‌گیرد؛ جواب اشتباه صفر. «قهرمان مسابقهٔ
          ما» در آخرین مرحله و روی جدول اعمال می‌شود — پس حدس‌زنندهٔ درست ممکن است
          خودش قهرمان شود!
        </p>
        {data.lock_at && (
          <p className="muted">
            {data.is_open ? "مهلت ثبت تا " : "مهلت ثبت (به پایان رسیده): "}
            <strong>{fmtDateTime(data.lock_at, tz)}</strong>
          </p>
        )}
        {data.settled && (
          <p className="badge-predicted">✓ امتیازها محاسبه شده‌اند</p>
        )}
        {!editable && !data.settled && (
          <p className="lock-on">
            زمان ویرایش پیش‌بینی‌های ویژه به پایان رسیده است.
          </p>
        )}
      </div>

      {data.questions.map((q) => {
        const state = saveState[q.kind] ?? "idle";
        const correctName = data.settled ? nameFor(q, q.correct) : null;
        return (
          <div className="card" key={q.kind}>
            <div className="pred-item">
              <div className="match-meta">
                <span className="stage-badge">{q.label}</span>
                <span className="muted">
                  {fa(q.points)} امتیاز
                </span>
              </div>
              <p className="muted">{q.description}</p>

              {editable ? (
                <div className="field">
                  <select
                    className="input"
                    value={picks[q.kind] === "" ? "" : String(picks[q.kind])}
                    onChange={(e) => onChange(q.kind, e.target.value)}
                  >
                    <option value="">— انتخاب کن —</option>
                    {options(q).map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  {state === "saved" && (
                    <span className="save-ok">✓ ذخیره شد</span>
                  )}
                  {state === "saving" && (
                    <span className="muted"> در حال ذخیره…</span>
                  )}
                  {state === "error" && (
                    <span className="save-err">ذخیره نشد</span>
                  )}
                </div>
              ) : (
                <div className="pred-actions">
                  <span>
                    پیش‌بینی تو:{" "}
                    <strong>{nameFor(q, q.my_pick)}</strong>
                  </span>
                  {data.settled && (
                    <span className="pred-action-right">
                      {q.my_correct ? (
                        <span className="save-ok">
                          ✓ درست — {fa(q.my_points ?? 0)} امتیاز
                        </span>
                      ) : (
                        <span className="muted">
                          جواب درست: <strong>{correctName}</strong>
                        </span>
                      )}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}
