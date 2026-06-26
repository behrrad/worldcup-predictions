"use client";

import { useMemo, useState } from "react";

import { fa } from "@/lib/format";
import {
  GEO,
  SERIES_COLORS,
  niceCeil,
  numLabel,
  stepLabel,
  xFor,
} from "@/lib/chart";
import type { ProgressionPlayer, ProgressionResp } from "@/lib/types";

/* A line per player: cumulative points, average points-per-prediction, or rank
 * after each finished match. Tick a player to add their line; switch metric with
 * the toggle. Drawn left-to-right (oldest match on the left) — the universal
 * time-series convention — inside a `dir="ltr"` box, while the Persian
 * legend/controls around it stay RTL. */

type Metric = "points" | "average" | "rank";

// How many players are pre-selected (you + the leaders) so the chart opens
// readable instead of as a tangle of every line at once.
const DEFAULT_LINES = 4;

const { W, H, PX0, PX1, PY0, PY1 } = GEO;

export default function ProgressionChart({ data }: { data: ProgressionResp }) {
  const { steps } = data;
  const n = steps.length;

  // Players sorted by final standing (best rank first; ties / no-rank by total),
  // which fixes their colour and the legend order.
  const players = useMemo(() => {
    return [...data.players].sort((a, b) => {
      const ra = a.rank ?? Number.POSITIVE_INFINITY;
      const rb = b.rank ?? Number.POSITIVE_INFINITY;
      return ra - rb || b.total - a.total;
    });
  }, [data.players]);

  const colorOf = useMemo(() => {
    const map = new Map<number, string>();
    players.forEach((p, i) =>
      map.set(p.id, SERIES_COLORS[i % SERIES_COLORS.length]),
    );
    return map;
  }, [players]);

  const [metric, setMetric] = useState<Metric>("points");
  const [hover, setHover] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(() => {
    const s = new Set<number>();
    const me = players.find((p) => p.is_me);
    if (me) s.add(me.id);
    for (const p of players) {
      if (s.size >= DEFAULT_LINES) break;
      s.add(p.id);
    }
    return s;
  });

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const shown = players.filter((p) => selected.has(p.id));
  const isRank = metric === "rank";

  // Average points per prediction (0 before they've predicted anything).
  const avgOf = (p: ProgressionPlayer, i: number) =>
    p.played[i] ? p.totals[i] / p.played[i] : 0;
  // The linear (bottom-anchored) value for the points/average metrics.
  const linearVal = (p: ProgressionPlayer, i: number) =>
    metric === "average" ? avgOf(p, i) : p.totals[i];
  const valueAt = (p: ProgressionPlayer, i: number) =>
    isRank ? p.ranks[i] : linearVal(p, i);

  // y-scales. Points/average: 0..nice(max of shown) with 0 at the bottom. Rank:
  // 1..N with rank 1 pinned to the top (so "up" always means "better").
  const scaleMax = useMemo(() => {
    let m = 0;
    for (const p of shown)
      for (let i = 0; i < n; i++) {
        const v = linearVal(p, i);
        if (v > m) m = v;
      }
    return niceCeil(m);
  }, [shown, metric, n]);
  const rankDenom = Math.max(1, players.length - 1);

  const yFor = (p: ProgressionPlayer, i: number): number =>
    isRank
      ? PY0 + ((p.ranks[i] - 1) / rankDenom) * (PY1 - PY0)
      : PY1 - (linearVal(p, i) / scaleMax) * (PY1 - PY0);

  // Horizontal gridlines + their axis labels.
  const yTicks: { y: number; label: string }[] = useMemo(() => {
    if (!isRank) {
      return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
        y: PY1 - f * (PY1 - PY0),
        label: numLabel(scaleMax * f),
      }));
    }
    const N = players.length;
    const ranks: number[] = [];
    if (N <= 8) {
      for (let r = 1; r <= N; r++) ranks.push(r);
    } else {
      for (let k = 0; k < 5; k++) ranks.push(1 + Math.round((k * (N - 1)) / 4));
    }
    return [...new Set(ranks)].map((r) => ({
      y: PY0 + ((r - 1) / rankDenom) * (PY1 - PY0),
      label: `#${fa(r)}`,
    }));
  }, [isRank, scaleMax, players.length, rankDenom]);

  // A handful of x ticks (matches are too dense to label them all).
  const xTicks: { x: number; label: string }[] = useMemo(() => {
    if (n === 0) return [];
    const count = Math.min(n, 7);
    const idx = new Set<number>();
    for (let t = 0; t < count; t++) {
      idx.add(count === 1 ? 0 : Math.round((t * (n - 1)) / (count - 1)));
    }
    return [...idx].map((i) => ({
      x: xFor(i, n),
      label: fa(steps[i].match_number ?? i + 1),
    }));
  }, [n, steps]);

  if (n === 0) {
    return (
      <div className="card center">
        <div className="recap-emoji">📈</div>
        <h2 className="card-title" style={{ justifyContent: "center" }}>
          هنوز روندی برای نمایش نیست
        </h2>
        <p className="muted">
          به‌محض اینکه اولین بازی‌ها تمام بشن، نمودار تغییر امتیاز و رتبهٔ
          بازیکنان اینجا ظاهر می‌شه.
        </p>
      </div>
    );
  }

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    const i = Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
    setHover(i);
  };

  // Tooltip anchor: above the topmost shown point at the hovered match.
  let tipLeft = 0;
  let tipTop = 0;
  if (hover !== null && shown.length) {
    tipLeft = (xFor(hover, n) / W) * 100;
    const topY = Math.min(...shown.map((p) => yFor(p, hover)));
    tipTop = (topY / H) * 100;
  }
  const tipRows =
    hover === null
      ? []
      : [...shown].sort((a, b) =>
          isRank
            ? valueAt(a, hover) - valueAt(b, hover) // better rank (smaller) first
            : valueAt(b, hover) - valueAt(a, hover), // more points/average first
        );

  return (
    <div className="prog">
      <div className="prog-toolbar">
        <div className="section-tabs" style={{ marginBottom: 0 }}>
          <button
            type="button"
            className={`tab ${metric === "points" ? "active" : ""}`}
            onClick={() => setMetric("points")}
          >
            امتیاز
          </button>
          <button
            type="button"
            className={`tab ${metric === "average" ? "active" : ""}`}
            onClick={() => setMetric("average")}
          >
            میانگین
          </button>
          <button
            type="button"
            className={`tab ${metric === "rank" ? "active" : ""}`}
            onClick={() => setMetric("rank")}
          >
            رتبه
          </button>
        </div>
        <div className="prog-actions">
          <button
            type="button"
            className="chip"
            onClick={() => setSelected(new Set(players.map((p) => p.id)))}
          >
            انتخاب همه
          </button>
          <button
            type="button"
            className="chip"
            onClick={() => setSelected(new Set())}
          >
            پاک کردن
          </button>
        </div>
      </div>

      <div className="card prog-chart-card">
        <div className="prog-wrap" dir="ltr">
          <svg
            className="prog-svg"
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label="نمودار روند امتیاز و رتبهٔ بازیکنان"
          >
            {/* horizontal gridlines + y labels */}
            {yTicks.map((t, k) => (
              <g key={`y${k}`}>
                <line
                  x1={PX0}
                  x2={PX1}
                  y1={t.y}
                  y2={t.y}
                  stroke="var(--line)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={PX0 - 8}
                  y={t.y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize={12}
                  fill="var(--muted)"
                >
                  {t.label}
                </text>
              </g>
            ))}

            {/* x ticks */}
            {xTicks.map((t, k) => (
              <text
                key={`x${k}`}
                x={t.x}
                y={PY1 + 18}
                textAnchor="middle"
                fontSize={12}
                fill="var(--muted)"
              >
                {t.label}
              </text>
            ))}

            {/* one polyline per shown player */}
            {shown.map((p) => {
              const pts = steps
                .map((_, i) => `${xFor(i, n)},${yFor(p, i)}`)
                .join(" ");
              const color = colorOf.get(p.id)!;
              const last = n - 1;
              return (
                <g key={p.id}>
                  <polyline
                    points={pts}
                    fill="none"
                    stroke={color}
                    strokeWidth={p.is_me ? 3.2 : 2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                    opacity={0.95}
                  />
                  {/* anchor dot on the latest match */}
                  <circle
                    cx={xFor(last, n)}
                    cy={yFor(p, last)}
                    r={3.6}
                    fill={color}
                    stroke="var(--surface)"
                    strokeWidth={1.5}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}

            {/* hover guide + dots */}
            {hover !== null && shown.length > 0 && (
              <g pointerEvents="none">
                <line
                  x1={xFor(hover, n)}
                  x2={xFor(hover, n)}
                  y1={PY0}
                  y2={PY1}
                  stroke="var(--line-strong)"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  vectorEffect="non-scaling-stroke"
                />
                {shown.map((p) => (
                  <circle
                    key={p.id}
                    cx={xFor(hover, n)}
                    cy={yFor(p, hover)}
                    r={4.2}
                    fill={colorOf.get(p.id)!}
                    stroke="#fff"
                    strokeWidth={1.5}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              </g>
            )}

            {/* transparent capture layer over the plot area */}
            <rect
              x={PX0}
              y={PY0}
              width={PX1 - PX0}
              height={PY1 - PY0}
              fill="transparent"
              style={{ touchAction: "none" }}
              onPointerMove={onMove}
              onPointerDown={onMove}
              onPointerLeave={() => setHover(null)}
            />
          </svg>

          {hover !== null && shown.length > 0 && (
            <div
              className="prog-tip"
              dir="rtl"
              style={{
                left: `${Math.max(13, Math.min(87, tipLeft))}%`,
                top: `${tipTop}%`,
              }}
            >
              <div className="prog-tip-title">{stepLabel(steps[hover])}</div>
              {tipRows.map((p) => (
                <div className="prog-tip-row" key={p.id}>
                  <span
                    className="prog-swatch"
                    style={{ background: colorOf.get(p.id)! }}
                  />
                  <span className="prog-tip-name">{p.name}</span>
                  <span className="prog-tip-val">
                    {isRank
                      ? `#${fa(p.ranks[hover])}`
                      : numLabel(linearVal(p, hover))}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <p className="prog-axis-note muted">
          محور افقی: شمارهٔ بازی‌های پایان‌یافته ·{" "}
          {metric === "points"
            ? "محور عمودی: مجموع امتیاز"
            : metric === "average"
              ? "محور عمودی: میانگین امتیاز هر پیش‌بینی"
              : "محور عمودی: رتبه (بالا = بهتر)"}
        </p>
      </div>

      {/* the player checkboxes (also the colour legend) */}
      <div className="card prog-legend-card">
        <p className="muted prog-legend-hint">
          بازیکنان را برای نمایش روی نمودار انتخاب کنید
        </p>
        <div className="prog-legend">
          {players.map((p) => {
            const on = selected.has(p.id);
            const color = colorOf.get(p.id)!;
            return (
              <button
                key={p.id}
                type="button"
                className={`prog-chip ${on ? "on" : "off"}`}
                aria-pressed={on}
                onClick={() => toggle(p.id)}
              >
                <span
                  className="prog-box"
                  style={{
                    background: on ? color : "transparent",
                    borderColor: color,
                  }}
                >
                  {on ? "✓" : ""}
                </span>
                <span className="prog-chip-name">
                  {p.name}
                  {p.is_me && <span className="muted"> (تو)</span>}
                </span>
                {p.rank != null && (
                  <span className="prog-chip-rank muted">#{fa(p.rank)}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
