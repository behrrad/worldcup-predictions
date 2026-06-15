"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  animate,
  AnimatePresence,
  motion,
  useMotionValue,
  useReducedMotion,
  type Variants,
} from "motion/react";

import { fa, fmtJalaliDay } from "@/lib/format";
import type {
  RecapCall,
  RecapMatchMini,
  RecapPlayer,
  RecapResp,
} from "@/lib/types";

// Drag distance (px) past which a horizontal swipe flips the card.
const SWIPE = 60;

// Map a scoring tier to the card's accent tone (matches the predictions board).
const TIER_TONE: Record<string, string> = {
  EXACT: "green",
  DIFF: "blue",
  WINNER: "gold",
};

/* ----------------------------- small helpers ----------------------------- */

function Avatar({ player, size = 56 }: { player: RecapPlayer; size?: number }) {
  if (player.avatar) {
    return (
      <img
        className="avatar recap-avatar"
        src={player.avatar}
        alt={player.name}
        width={size}
        height={size}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      className="avatar avatar-fallback recap-avatar"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      {player.name.slice(0, 1)}
    </span>
  );
}

/** A number that counts up from 0 when its card appears. */
function CountUp({ value, decimals }: { value: number; decimals?: number }) {
  const dec = decimals ?? (Number.isInteger(value) ? 0 : 1);
  const mv = useMotionValue(0);
  const [shown, setShown] = useState(value.toFixed(dec));
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce) {
      setShown(value.toFixed(dec));
      return;
    }
    const controls = animate(mv, value, {
      duration: 0.9,
      ease: "easeOut",
      onUpdate: (v) => setShown(v.toFixed(dec)),
    });
    return () => controls.stop();
  }, [value, dec, reduce, mv]);

  return <>{fa(shown)}</>;
}

/** A finished fixture: home flag/name · final score · away flag/name. */
function MatchLine({ m }: { m: RecapMatchMini }) {
  return (
    <div className="recap-match">
      <span className="recap-side">
        <span className="flag">{m.home_team?.flag}</span>
        <span>{m.home_team?.name ?? m.home_label ?? "؟"}</span>
      </span>
      <span className="recap-match-score">
        {fa(m.home_score ?? "—")} : {fa(m.away_score ?? "—")}
      </span>
      <span className="recap-side away">
        <span>{m.away_team?.name ?? m.away_label ?? "؟"}</span>
        <span className="flag">{m.away_team?.flag}</span>
      </span>
    </div>
  );
}

/** A standout prediction: the fixture, the pick, and the points earned. */
function CallBlock({ call }: { call: RecapCall }) {
  return (
    <div className="recap-call">
      <span className="stage-badge">{call.match.stage_label}</span>
      <MatchLine m={call.match} />
      <div className="recap-call-meta">
        <span>
          پیش‌بینی: <b>{fa(call.prediction.home)} : {fa(call.prediction.away)}</b>
        </span>
        <span className={`recap-points-pill tone-${TIER_TONE[call.tier] ?? "neutral"}`}>
          +{fa(call.points)} امتیاز
          {call.tier_label ? ` · ${call.tier_label}` : ""}
        </span>
      </div>
    </div>
  );
}

const listV: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.25 } },
};
const itemV: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
};

/* -------------------------------- cards ---------------------------------- */
// Each entry is rendered inside one animated story card; `tone` sets the accent.
type Card = { key: string; tone: string; node: React.ReactNode };

function buildCards(recap: RecapResp, slug: string): Card[] {
  const { me, general, matches, date } = recap;
  const cards: Card[] = [];
  const heads = (s: number) => fa(s);

  // 1) Intro — the matchday and its results.
  cards.push({
    key: "intro",
    tone: "intro",
    node: (
      <>
        <p className="recap-eyebrow">جمع‌بندی روز</p>
        <h2 className="recap-headline">{date ? fmtJalaliDay(date) : ""}</h2>
        <p className="recap-sub">
          {heads(matches.length)} بازی این روز به پایان رسید
        </p>
        <motion.div
          className="recap-results"
          variants={listV}
          initial="hidden"
          animate="show"
        >
          {matches.map((m) => (
            <motion.div key={m.id} variants={itemV}>
              <MatchLine m={m} />
            </motion.div>
          ))}
        </motion.div>
        <p className="recap-hint">برای دیدن جزئیات روز، ورق بزن →</p>
      </>
    ),
  });

  // 2) Your day — points + the breakdown of how you got there.
  if (me) {
    const hitRow = (n: number, label: string, tone: string) =>
      n > 0 ? (
        <motion.span variants={itemV} className={`recap-hit tone-${tone}`}>
          {heads(n)} {label}
        </motion.span>
      ) : null;
    cards.push({
      key: "you",
      tone: me.participated ? "you" : "muted",
      node: me.participated ? (
        <>
          <p className="recap-eyebrow">روزِ تو</p>
          <div className="recap-big">
            <CountUp value={me.points} />
          </div>
          <p className="recap-sub">
            امتیاز از {heads(me.predicted)} پیش‌بینی
            {me.is_top_scorer && <b className="recap-flag-top"> · بیشترین امتیاز روز 🏆</b>}
          </p>
          <motion.div
            className="recap-hits"
            variants={listV}
            initial="hidden"
            animate="show"
          >
            {hitRow(me.hits.exact, "نتیجهٔ دقیق", "green")}
            {hitRow(me.hits.diff, "برنده + اختلاف", "blue")}
            {hitRow(me.hits.winner, "برندهٔ درست", "gold")}
            {hitRow(me.hits.participation, "شرکت", "neutral")}
            {hitRow(me.hits.missed, "بدون پیش‌بینی", "red")}
          </motion.div>
          <p className="recap-hint">
            میانگین روزِ مسابقه: {fa(me.day_avg)} امتیاز
          </p>
        </>
      ) : (
        <>
          <p className="recap-eyebrow">روزِ تو</p>
          <div className="recap-emoji">😴</div>
          <h2 className="recap-headline">این روز پیش‌بینی نکردی</h2>
          <p className="recap-sub">
            دفعهٔ بعد جا نمون — هر بازی می‌تونه رتبه‌ت رو جابه‌جا کنه.
          </p>
        </>
      ),
    });

    // 3) Your best call.
    if (me.best_call) {
      cards.push({
        key: "you-best",
        tone: TIER_TONE[me.best_call.tier] ?? "you",
        node: (
          <>
            <p className="recap-eyebrow">بهترین پیش‌بینی تو</p>
            <div className="recap-emoji">🎯</div>
            <CallBlock call={me.best_call} />
          </>
        ),
      });
    }

    // 4) Your rank movement across the day.
    const climbed = me.rank_delta > 0;
    const dropped = me.rank_delta < 0;
    cards.push({
      key: "you-rank",
      tone: climbed ? "gold" : "rank",
      node: (
        <>
          <p className="recap-eyebrow">رتبهٔ تو</p>
          <div className="recap-rank-move">
            <span className="recap-rank-from">{fa(me.rank_before)}</span>
            <span className="recap-rank-arrow">←</span>
            <span className={`recap-rank-to ${climbed ? "up" : dropped ? "down" : ""}`}>
              <CountUp value={me.rank_after} />
            </span>
          </div>
          <p className="recap-sub">
            {climbed
              ? `${heads(me.rank_delta)} پله بالا رفتی ▲`
              : dropped
                ? `${heads(-me.rank_delta)} پله پایین اومدی ▼`
                : "رتبه‌ت ثابت موند"}
          </p>
          <p className="recap-hint">مجموع امتیازت: {fa(me.total_after)}</p>
        </>
      ),
    });
  }

  // 5) Top scorer of the day.
  if (general?.top_scorer) {
    const t = general.top_scorer;
    cards.push({
      key: "top",
      tone: "gold",
      node: (
        <>
          <p className="recap-eyebrow">ستارهٔ روز</p>
          <Avatar player={t} size={84} />
          <h2 className="recap-headline">
            {t.name}
            {t.is_me && <span className="muted"> (تو)</span>}
          </h2>
          <div className="recap-big tone-gold">
            <CountUp value={t.points} />
          </div>
          <p className="recap-sub">
            بیشترین امتیاز روز
            {t.ties > 0 && ` (مشترک با ${heads(t.ties)} نفر دیگر)`}
          </p>
        </>
      ),
    });
  }

  // 6) Best single call across the league.
  if (general?.best_call) {
    const b = general.best_call;
    cards.push({
      key: "best",
      tone: TIER_TONE[b.tier] ?? "blue",
      node: (
        <>
          <p className="recap-eyebrow">پیش‌بینی روز</p>
          <div className="recap-author">
            <Avatar player={b} size={44} />
            <strong>
              {b.name}
              {b.is_me && <span className="muted"> (تو)</span>}
            </strong>
          </div>
          <CallBlock call={b} />
          <p className="recap-hint">
            {b.also_count === 0
              ? "تنها کسی که این رو درست زد!"
              : `${heads(b.also_count)} نفر دیگه هم به همین خوبی زدن`}
          </p>
        </>
      ),
    });
  }

  // 7) The upset — the match fewest people called.
  if (general?.surprise) {
    const s = general.surprise;
    cards.push({
      key: "surprise",
      tone: "red",
      node: (
        <>
          <p className="recap-eyebrow">شگفتی روز</p>
          <div className="recap-emoji">😱</div>
          <MatchLine m={s.match} />
          <p className="recap-sub">
            فقط {heads(s.correct_count)} از {heads(s.predicted_count)} نفر برنده رو
            درست زدن
          </p>
        </>
      ),
    });
  }

  // 8) Biggest climber of the day.
  if (general?.mover) {
    const mv = general.mover;
    cards.push({
      key: "mover",
      tone: "green",
      node: (
        <>
          <p className="recap-eyebrow">صعود روز</p>
          <div className="recap-emoji">🚀</div>
          <Avatar player={mv} size={72} />
          <h2 className="recap-headline">
            {mv.name}
            {mv.is_me && <span className="muted"> (تو)</span>}
          </h2>
          <p className="recap-sub">
            از رتبهٔ {fa(mv.from_rank)} به {fa(mv.to_rank)} — {heads(mv.delta)} پله بالاتر ▲
          </p>
        </>
      ),
    });
  }

  // 9) Closing podium — current standings, with a link to the full table.
  if (general?.podium.length) {
    cards.push({
      key: "podium",
      tone: "podium",
      node: (
        <>
          <p className="recap-eyebrow">جدول تا اینجا</p>
          <div className="recap-emoji">🏆</div>
          <div className="recap-podium">
            {general.podium.map((p) => (
              <div
                key={p.id}
                className={`recap-podium-row rank-${p.rank} ${p.is_me ? "me" : ""}`}
              >
                <span className="recap-podium-rank">
                  {["🥇", "🥈", "🥉"][p.rank - 1] ?? fa(p.rank)}
                </span>
                <Avatar player={p} size={40} />
                <span className="recap-podium-name">
                  {p.name}
                  {p.is_me && <span className="muted"> (تو)</span>}
                </span>
                <span className="pts">{fa(p.total)}</span>
              </div>
            ))}
          </div>
          <Link className="btn btn-pitch btn-block mt" href={`/l/${slug}/leaderboard`}>
            جدول کامل
          </Link>
        </>
      ),
    });
  }

  return cards;
}

/* ----------------------------- the story UI ------------------------------ */

export default function RecapStory({
  slug,
  recap,
  staticAll = false,
}: {
  slug: string;
  recap: RecapResp;
  // Demo/debug: render every card stacked (no interaction) so the whole story
  // can be captured at once. Off in the real app.
  staticAll?: boolean;
}) {
  const reduce = useReducedMotion();
  const cards = useMemo(() => buildCards(recap, slug), [recap, slug]);
  const total = cards.length;

  const [[index, dir], setState] = useState<[number, number]>([0, 0]);

  const go = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(total - 1, next));
      setState(([cur]) => (clamped === cur ? [cur, 0] : [clamped, clamped > cur ? 1 : -1]));
    },
    [total],
  );

  // RTL: ← advances, → goes back; space/enter advance.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" || e.key === " " || e.key === "Enter") go(index + 1);
      else if (e.key === "ArrowRight") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  // Empty state: nothing has finished yet.
  if (!recap.date) {
    return (
      <div className="card recap-empty">
        <div className="recap-emoji">🗓️</div>
        <h2 className="card-title">هنوز جمع‌بندی‌ای نیست</h2>
        <p className="muted">
          به‌محض اینکه اولین بازی‌ها تمام بشن، جمع‌بندی روز اینجا ظاهر می‌شه.
        </p>
      </div>
    );
  }

  // Demo/debug: every card stacked, no interaction, so a single screenshot
  // shows the whole story.
  if (staticAll) {
    return (
      <div className="recap">
        <div className="recap-head">
          <span className="recap-day-label">{fmtJalaliDay(recap.date)}</span>
        </div>
        {cards.map((c) => (
          <div key={c.key} className={`recap-card recap-card-static tone-${c.tone}`}>
            <div className="recap-card-body">{c.node}</div>
          </div>
        ))}
      </div>
    );
  }

  const dates = recap.available_dates;
  const dayIdx = recap.date ? dates.indexOf(recap.date) : -1;
  const prevDay = dayIdx > 0 ? dates[dayIdx - 1] : null;
  const nextDay = dayIdx >= 0 && dayIdx < dates.length - 1 ? dates[dayIdx + 1] : null;

  const cardVariants: Variants = reduce
    ? {
        enter: { opacity: 0 },
        center: { opacity: 1 },
        exit: { opacity: 0 },
      }
    : {
        enter: (d: number) => ({ opacity: 0, x: d >= 0 ? 64 : -64, scale: 0.97 }),
        center: { opacity: 1, x: 0, scale: 1 },
        exit: (d: number) => ({ opacity: 0, x: d >= 0 ? -64 : 64, scale: 0.97 }),
      };

  return (
    <div className="recap">
      {/* Matchday header + day-to-day navigation. */}
      <div className="recap-head">
        <Link
          className={`btn btn-outline btn-sm ${prevDay ? "" : "is-disabled"}`}
          href={prevDay ? `/l/${slug}/recap?date=${prevDay}` : "#"}
          aria-disabled={!prevDay}
        >
          روز قبل →
        </Link>
        <span className="recap-day-label">{fmtJalaliDay(recap.date)}</span>
        <Link
          className={`btn btn-outline btn-sm ${nextDay ? "" : "is-disabled"}`}
          href={nextDay ? `/l/${slug}/recap?date=${nextDay}` : "#"}
          aria-disabled={!nextDay}
        >
          ← روز بعد
        </Link>
      </div>

      {/* Progress dots. */}
      <div className="recap-dots">
        {Array.from({ length: total }).map((_, i) => (
          <button
            key={i}
            type="button"
            className={`recap-dot ${i === index ? "active" : ""}`}
            aria-label={`کارت ${fa(i + 1)}`}
            onClick={() => go(i)}
          />
        ))}
      </div>

      {/* The animated card stage. */}
      <div className="recap-stage">
        <AnimatePresence mode="wait" custom={dir} initial={false}>
          <motion.div
            key={index}
            className={`recap-card tone-${cards[index]?.tone}`}
            custom={dir}
            variants={cardVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: reduce ? 0.2 : 0.42, ease: [0.22, 1, 0.36, 1] }}
            drag={reduce ? false : "x"}
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.18}
            onDragEnd={(_, info) => {
              if (info.offset.x < -SWIPE) go(index + 1);
              else if (info.offset.x > SWIPE) go(index - 1);
            }}
          >
            <div className="recap-card-body">{cards[index]?.node}</div>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Explicit prev/next controls (RTL order: next on the left). */}
      <div className="recap-nav">
        <button
          type="button"
          className="btn btn-outline"
          onClick={() => go(index + 1)}
          disabled={index >= total - 1}
        >
          بعدی ←
        </button>
        <span className="recap-counter">
          {fa(index + 1)} / {fa(total)}
        </span>
        <button
          type="button"
          className="btn btn-outline"
          onClick={() => go(index - 1)}
          disabled={index <= 0}
        >
          → قبلی
        </button>
      </div>
    </div>
  );
}
