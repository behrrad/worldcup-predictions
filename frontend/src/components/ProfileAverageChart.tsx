"use client";

import { useMemo, useState } from "react";

import { fa } from "@/lib/format";
import { GEO, niceCeil, numLabel, stepLabel, xFor } from "@/lib/chart";
import type { PlayerAverageResp } from "@/lib/types";

/* A single player's form over time, pooled across every league they're in:
 * either the running average points-per-prediction (default) or the cumulative
 * total. Same SVG/geometry as the league chart, but one line and no player
 * toggles — a profile is one person. Drawn left-to-right inside a `dir="ltr"`
 * box while the Persian chrome stays RTL. */

type Metric = "average" | "total";

const { W, H, PX0, PX1, PY0, PY1 } = GEO;
const ACCENT = "#2b6cff";

export default function ProfileAverageChart({
  data,
}: {
  data: PlayerAverageResp;
}) {
  const { steps, series } = data;
  const n = steps.length;
  const [metric, setMetric] = useState<Metric>("average");
  const [hover, setHover] = useState<number | null>(null);

  const valueAt = (i: number) =>
    metric === "average" ? series.averages[i] : series.totals[i];

  const scaleMax = useMemo(() => {
    const arr = metric === "average" ? series.averages : series.totals;
    let m = 0;
    for (const v of arr) if (v > m) m = v;
    return niceCeil(m);
  }, [metric, series]);

  const yFor = (i: number) => PY1 - (valueAt(i) / scaleMax) * (PY1 - PY0);

  const yTicks = useMemo(
    () =>
      [0, 0.25, 0.5, 0.75, 1].map((f) => ({
        y: PY1 - f * (PY1 - PY0),
        label: numLabel(scaleMax * f),
      })),
    [scaleMax],
  );

  const xTicks = useMemo(() => {
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
      <p className="muted" style={{ margin: 0 }}>
        وقتی اولین پیش‌بینی‌های این بازیکن امتیاز بگیرن، روند میانگین امتیازش
        اینجا نشون داده می‌شه.
      </p>
    );
  }

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1)))));
  };

  const linePts = steps.map((_, i) => `${xFor(i, n)},${yFor(i)}`).join(" ");
  const tipLeft = hover === null ? 0 : (xFor(hover, n) / W) * 100;
  const tipTop = hover === null ? 0 : (yFor(hover) / H) * 100;

  return (
    <div className="prof-chart">
      <div className="section-tabs" style={{ marginBottom: 14 }}>
        <button
          type="button"
          className={`tab ${metric === "average" ? "active" : ""}`}
          onClick={() => setMetric("average")}
        >
          میانگین هر پیش‌بینی
        </button>
        <button
          type="button"
          className={`tab ${metric === "total" ? "active" : ""}`}
          onClick={() => setMetric("total")}
        >
          مجموع امتیاز
        </button>
      </div>

      <div className="prog-wrap" dir="ltr">
        <svg
          className="prog-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="نمودار روند میانگین امتیاز بازیکن"
        >
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

          <polyline
            points={linePts}
            fill="none"
            stroke={ACCENT}
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          <circle
            cx={xFor(n - 1, n)}
            cy={yFor(n - 1)}
            r={3.8}
            fill={ACCENT}
            stroke="var(--surface)"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
          />

          {hover !== null && (
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
              <circle
                cx={xFor(hover, n)}
                cy={yFor(hover)}
                r={4.2}
                fill={ACCENT}
                stroke="#fff"
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          )}

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

        {hover !== null && (
          <div
            className="prog-tip"
            dir="rtl"
            style={{
              left: `${Math.max(13, Math.min(87, tipLeft))}%`,
              top: `${tipTop}%`,
            }}
          >
            <div className="prog-tip-title">{stepLabel(steps[hover])}</div>
            <div className="prog-tip-row">
              <span className="prog-tip-name">میانگین</span>
              <span className="prog-tip-val">
                {numLabel(series.averages[hover])}
              </span>
            </div>
            <div className="prog-tip-row">
              <span className="prog-tip-name">مجموع</span>
              <span className="prog-tip-val">
                {numLabel(series.totals[hover])} · {fa(series.played[hover])}{" "}
                پیش‌بینی
              </span>
            </div>
          </div>
        )}
      </div>
      <p className="prog-axis-note muted">
        محور افقی: شمارهٔ بازی‌های پایان‌یافته ·{" "}
        {metric === "average"
          ? "محور عمودی: میانگین امتیاز هر پیش‌بینی (همهٔ مسابقه‌ها)"
          : "محور عمودی: مجموع امتیاز (همهٔ مسابقه‌ها)"}
      </p>
    </div>
  );
}
