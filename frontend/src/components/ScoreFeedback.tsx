import type { Evaluation } from "../api/types";

function scoreColor(score?: number) {
  if (score == null) return "bg-navy/10 text-navy/60";
  if (score >= 4) return "bg-green-100 text-green-700";
  if (score >= 3) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

export function ScoreFeedback({ evaluation }: { evaluation: Evaluation }) {
  const e = evaluation;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full px-3 py-1 font-semibold ${scoreColor(e.overall_score)}`}>
          Score {e.overall_score ?? "N/A"}/5
        </span>
        {e.overall_rating && <span className="text-navy/60">{e.overall_rating}</span>}
        {e.hiring_signal && (
          <span className="rounded-full bg-navy/5 px-3 py-1 text-xs">
            signal: {e.hiring_signal}
          </span>
        )}
      </div>

      {e.summary && <p className="text-navy/70">{e.summary}</p>}

      {!!e.criteria_scores?.length && (
        <div className="space-y-2">
          {e.criteria_scores.map((c, i) => (
            <div key={i} className="rounded-2xl border border-navy/10 p-3">
              <div className="flex items-center justify-between font-medium">
                <span>{c.criterion}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${scoreColor(c.score)}`}>
                  {c.score}/5
                </span>
              </div>
              {c.reason && <p className="mt-1 text-navy/60">{c.reason}</p>}
              {c.improvement_advice && (
                <p className="mt-1 text-brand-600">💡 {c.improvement_advice}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {!!e.strengths?.length && (
          <div>
            <p className="font-semibold text-green-700">Strengths</p>
            <ul className="mt-1 list-disc pl-5 text-navy/70">
              {e.strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        {!!e.weaknesses?.length && (
          <div>
            <p className="font-semibold text-rose-700">Weaknesses</p>
            <ul className="mt-1 list-disc pl-5 text-navy/70">
              {e.weaknesses.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
      </div>

      {e.candidate_coaching?.better_answer_strategy && (
        <div className="rounded-2xl border border-brand/20 bg-brand/5 p-3">
          <p className="font-semibold text-brand-600">Coaching</p>
          <p className="mt-1 text-navy/70">
            {e.candidate_coaching.better_answer_strategy}
          </p>
        </div>
      )}
    </div>
  );
}
