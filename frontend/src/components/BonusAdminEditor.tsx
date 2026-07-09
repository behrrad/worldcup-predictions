"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { apiFetch } from "@/lib/api";
import { fa } from "@/lib/format";
import type {
  AdminBonusLeagueT,
  AdminBonusPayload,
  AdminBonusQuestionMeta,
} from "@/lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";
type Drafts = Record<number, Record<string, string>>; // membershipId -> kind -> value

export default function BonusAdminEditor({
  leagues,
}: {
  leagues: AdminBonusLeagueT[];
}) {
  const { getToken } = useAuth();
  const [slug, setSlug] = useState<string>("");
  const [payload, setPayload] = useState<AdminBonusPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});

  function draftsFrom(p: AdminBonusPayload): Drafts {
    const d: Drafts = {};
    for (const m of p.members) {
      d[m.membership_id] = {};
      for (const q of p.questions) {
        const v = m.picks[q.kind];
        d[m.membership_id][q.kind] = v != null ? String(v) : "";
      }
    }
    return d;
  }

  async function loadLeague(s: string) {
    setSlug(s);
    setPayload(null);
    if (!s) return;
    setLoading(true);
    try {
      const token = await getToken();
      const p = (await apiFetch(`/admin/leagues/${s}/bonus/`, token)) as AdminBonusPayload;
      setPayload(p);
      setDrafts(draftsFrom(p));
      setSaveState({});
    } finally {
      setLoading(false);
    }
  }

  // id -> label lookups per answer type.
  const teamLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const t of payload?.teams ?? [])
      m.set(t.id, `${t.flag ? t.flag + " " : ""}${t.name}`);
    return m;
  }, [payload]);
  const playerLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of payload?.players ?? [])
      m.set(p.id, p.team ? `${p.name} (${p.team.name})` : p.name);
    return m;
  }, [payload]);
  const memberLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const o of payload?.members_options ?? []) m.set(o.id, o.name);
    return m;
  }, [payload]);

  function optionsFor(q: AdminBonusQuestionMeta): { id: number; label: string }[] {
    const map =
      q.answer_type === "team"
        ? teamLabel
        : q.answer_type === "player"
          ? playerLabel
          : memberLabel;
    return [...map.entries()].map(([id, label]) => ({ id, label }));
  }

  function setDraft(mid: number, kind: string, value: string) {
    setDrafts((d) => ({ ...d, [mid]: { ...d[mid], [kind]: value } }));
    setSaveState((s) => ({ ...s, [mid]: "idle" }));
  }

  async function save(mid: number) {
    if (!payload) return;
    setSaveState((s) => ({ ...s, [mid]: "saving" }));
    try {
      const token = await getToken();
      const picks = payload.questions.map((q) => ({
        kind: q.kind,
        value: drafts[mid][q.kind] === "" ? null : Number(drafts[mid][q.kind]),
      }));
      const res = (await apiFetch(`/admin/leagues/${slug}/bonus/`, token, {
        method: "POST",
        body: JSON.stringify({ membership_id: mid, picks }),
      })) as { saved: number; member: { picks: Record<string, number | null> } };
      // Reflect the server's stored state back into the draft + member list.
      setPayload((p) =>
        p
          ? {
              ...p,
              members: p.members.map((m) =>
                m.membership_id === mid
                  ? {
                      ...m,
                      picks: res.member.picks,
                      count: Object.keys(res.member.picks).length,
                      completed:
                        Object.keys(res.member.picks).length >= p.questions.length,
                    }
                  : m,
              ),
            }
          : p,
      );
      setSaveState((s) => ({ ...s, [mid]: "saved" }));
    } catch {
      setSaveState((s) => ({ ...s, [mid]: "error" }));
    }
  }

  return (
    <>
      <div className="card">
        <div className="field" style={{ marginBottom: 0 }}>
          <label>مسابقه</label>
          <select
            className="input"
            value={slug}
            onChange={(e) => loadLeague(e.target.value)}
          >
            <option value="">— انتخاب مسابقه —</option>
            {leagues.map((l) => (
              <option key={l.slug} value={l.slug}>
                {l.name} — {fa(l.completed_count)}/{fa(l.member_count)} تکمیل‌شده
                {l.bonus_enabled ? "" : " (غیرفعال)"}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div className="card">
          <div className="empty">در حال بارگذاری…</div>
        </div>
      )}

      {payload &&
        payload.members.map((m) => {
          const state = saveState[m.membership_id] ?? "idle";
          return (
            <div className="card" key={m.membership_id}>
              <div className="match-meta">
                <span className="stage-badge">{m.name}</span>
                {m.completed ? (
                  <span className="badge-predicted">✓ تکمیل</span>
                ) : (
                  <span className="muted">
                    {fa(m.count)}/{fa(payload.questions.length)}
                  </span>
                )}
              </div>
              {payload.questions.map((q) => (
                <div className="field" key={q.kind}>
                  <label>
                    {q.label}{" "}
                    <span className="muted">({fa(q.points)} امتیاز)</span>
                  </label>
                  <select
                    className="input"
                    value={drafts[m.membership_id]?.[q.kind] ?? ""}
                    onChange={(e) => setDraft(m.membership_id, q.kind, e.target.value)}
                  >
                    <option value="">— بدون انتخاب —</option>
                    {optionsFor(q).map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              <div className="pred-actions">
                <span className="pred-action-right">
                  {state === "saved" && <span className="save-ok">✓ ذخیره شد</span>}
                  {state === "error" && <span className="save-err">خطا</span>}
                  <button
                    type="button"
                    className="btn btn-pitch btn-sm"
                    disabled={state === "saving"}
                    onClick={() => save(m.membership_id)}
                  >
                    {state === "saving" ? "در حال ذخیره…" : "ذخیرهٔ پیش‌بینی‌ها"}
                  </button>
                </span>
              </div>
            </div>
          );
        })}
    </>
  );
}
