import GlobalScoreboard from "@/components/GlobalScoreboard";
import { fa } from "@/lib/format";
import { serverFetch } from "@/lib/server";
import type { GlobalScoreboardResp } from "@/lib/types";

export const metadata = { title: "جدول کل بازیکنان" };

// Public page (not in the proxy.ts protected matcher): signed-out visitors see
// the same board, just without their own row highlighted.
export default async function ScoreboardPage() {
  const board = (await serverFetch("/scoreboard/")) as GlobalScoreboardResp;

  return (
    <>
      <div className="page-head">
        <h1>جدول کل بازیکنان</h1>
        <p>
          همهٔ بازیکنان سایت روی یک مقیاس منصفانه (ضریب ×۱ برای همهٔ بازی‌ها)
          {board.finished_count > 0 && (
            <> · {fa(board.finished_count)} بازی انجام شده</>
          )}
        </p>
      </div>
      <GlobalScoreboard board={board} />
    </>
  );
}
