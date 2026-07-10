import type { BonusAllResp } from "@/lib/types";

// Everyone's bonus picks, shown once the deadline passes. The «قهرمان مسابقهٔ ما»
// picks stay hidden until the final settlement (so the ending isn't spoiled).
export default function BonusReveal({ data }: { data: BonusAllResp }) {
  if (!data.enabled) return null;

  return (
    <div className="card">
      <h2 className="card-title">👀 پیش‌بینی‌های ویژهٔ همه</h2>

      {!data.revealed ? (
        <div className="empty">
          پس از پایان مهلت، پیش‌بینی‌های ویژهٔ همهٔ اعضا اینجا نمایش داده می‌شود.
        </div>
      ) : (
        data.questions.map((q) => (
          <div key={q.kind}>
            <div className="day-header">{q.label}</div>
            {q.hidden ? (
              <p className="muted">
                🔒 پیش‌بینی «قهرمان مسابقهٔ ما» در پایان تورنمنت و هنگام محاسبهٔ
                نهایی فاش می‌شود.
              </p>
            ) : q.picks.length === 0 ? (
              <p className="muted">کسی این مورد را پیش‌بینی نکرده است.</p>
            ) : (
              <table className="table">
                <tbody>
                  {q.picks.map((p, i) => (
                    <tr key={i} className={p.is_me ? "rank-1" : ""}>
                      <td>
                        {p.name}
                        {p.is_me ? " (تو)" : ""}
                      </td>
                      <td>
                        {p.flag ? p.flag + " " : ""}
                        {p.answer}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))
      )}
    </div>
  );
}
