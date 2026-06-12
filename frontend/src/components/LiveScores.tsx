"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { fa } from "@/lib/format";
import type { LiveMatchT, LiveScoresResp } from "@/lib/types";

const POLL_MS = 45_000;

/**
 * The live-score strip: polls /api/live/ while the tab is visible and shows
 * every match that's in play right now (score, minute, status). Renders
 * nothing when no match is live. When a *score* changes (a goal — not the
 * ticking minute) it also refreshes the route so server-rendered match lists
 * pick up the new numbers.
 */
export default function LiveScores() {
  const { getToken } = useAuth();
  const router = useRouter();
  const [matches, setMatches] = useState<LiveMatchT[]>([]);
  // The last seen "goals state"; only a change here warrants a router.refresh.
  const scoreHash = useRef("");

  const poll = useCallback(async () => {
    if (document.hidden) return; // nobody's watching; don't burn requests
    try {
      const token = await getToken();
      const res = (await apiFetch("/live/", token)) as LiveScoresResp;
      setMatches(res.matches);
      const hash = res.matches
        .map((m) => `${m.id}:${m.home}-${m.away}:${m.status}`)
        .join("|");
      if (scoreHash.current && hash !== scoreHash.current) {
        router.refresh(); // a goal went in — re-render the server components
      }
      scoreHash.current = hash;
    } catch {
      // Keep showing the last known state; the next poll will retry.
    }
  }, [getToken, router]);

  useEffect(() => {
    poll();
    const timer = setInterval(poll, POLL_MS);
    // Catch up immediately when the user returns to the tab.
    const onVisible = () => {
      if (!document.hidden) poll();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [poll]);

  if (matches.length === 0) return null;

  return (
    <div className="live-strip">
      {matches.map((m) => (
        <div key={m.id} className="live-chip">
          <span className="live-badge">
            {m.status === "LIVE" && <span className="live-dot" />}
            {m.status === "LIVE" && m.minute
              ? `${fa(m.minute)}′`
              : m.status_label}
          </span>
          <span className="live-team">
            {m.home_team?.flag} {m.home_team?.name ?? "؟"}
          </span>
          <span className="live-score">
            {fa(m.home ?? "؟")} : {fa(m.away ?? "؟")}
          </span>
          <span className="live-team">
            {m.away_team?.name ?? "؟"} {m.away_team?.flag}
          </span>
        </div>
      ))}
    </div>
  );
}
