import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { MockReview as MockReviewData, MockReviewTurn } from "../api/types";
import { Button, ErrorNote, PageHeader, Spinner } from "../components/ui";

function Section({
  title,
  items,
  tone = "navy",
}: {
  title: string;
  items?: string[];
  tone?: "navy" | "green" | "amber" | "brand";
}) {
  if (!items?.length) return null;
  const dot =
    tone === "green"
      ? "bg-green-500"
      : tone === "amber"
      ? "bg-amber-500"
      : tone === "brand"
      ? "bg-brand"
      : "bg-navy/40";
  return (
    <div className="card p-6">
      <h3 className="font-bold">{title}</h3>
      <ul className="mt-3 space-y-2">
        {items.map((it, i) => (
          <li key={i} className="flex gap-3 text-navy/80">
            <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function scoreBadge(score?: number) {
  if (typeof score !== "number") return null;
  const tone =
    score >= 4 ? "bg-green-500" : score >= 3 ? "bg-amber-500" : "bg-rose-500";
  return (
    <span
      className={`rounded-full ${tone} px-3 py-1 font-mono text-xs text-white`}
    >
      {score.toFixed(1)}/5
    </span>
  );
}

function QuestionCard({ turn, number }: { turn: MockReviewTurn; number: number }) {
  return (
    <div
      className={`card p-6 ${
        turn.is_follow_up ? "border-l-4 border-l-amber-400 md:ml-6" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-bold uppercase tracking-wide text-navy/40">
          {turn.is_follow_up ? `↳ Follow-up to Q${number}` : `Question ${number}`}
          {turn.competency ? ` · ${turn.competency}` : ""}
        </p>
        {scoreBadge(turn.overall_score)}
      </div>
      <p className="mt-2 font-semibold leading-relaxed">{turn.question}</p>

      <p className="mt-4 text-xs font-bold uppercase tracking-wide text-navy/40">
        Your answer
      </p>
      <p className="mt-1 whitespace-pre-wrap text-sm text-navy/70">
        {turn.answer || "—"}
      </p>

      {turn.summary && (
        <p className="mt-4 rounded-2xl bg-navy/5 px-4 py-3 text-sm text-navy/80">
          {turn.summary}
        </p>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {!!turn.strengths?.length && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-green-600">
              Strengths
            </p>
            <ul className="mt-2 space-y-1 text-sm text-navy/70">
              {turn.strengths.map((s, i) => (
                <li key={i}>• {s}</li>
              ))}
            </ul>
          </div>
        )}
        {!!turn.weaknesses?.length && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-amber-600">
              To improve
            </p>
            <ul className="mt-2 space-y-1 text-sm text-navy/70">
              {turn.weaknesses.map((w, i) => (
                <li key={i}>• {w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <DeliveryBlock delivery={turn.delivery_assessment} />
    </div>
  );
}

function DeliveryBlock({
  delivery,
}: {
  delivery?: MockReviewTurn["delivery_assessment"];
}) {
  if (!delivery) return null;
  const {
    fluency_rating,
    voice_steadiness,
    body_language_rating,
    observations,
    impact_on_communication,
  } = delivery;
  const hasAny =
    fluency_rating ||
    voice_steadiness ||
    body_language_rating ||
    impact_on_communication ||
    (observations && observations.length > 0);
  if (!hasAny) return null;

  return (
    <div className="mt-4 rounded-2xl border border-navy/10 bg-navy/[0.03] px-4 py-3">
      <p className="text-xs font-bold uppercase tracking-wide text-navy/40">
        🎥 Delivery &amp; presentation
      </p>
      {(fluency_rating || voice_steadiness || body_language_rating) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {fluency_rating && (
            <span className="rounded-full bg-white px-3 py-1 text-xs text-navy/70 ring-1 ring-navy/10">
              Fluency: <b>{fluency_rating}</b>
            </span>
          )}
          {voice_steadiness && (
            <span className="rounded-full bg-white px-3 py-1 text-xs text-navy/70 ring-1 ring-navy/10">
              Voice: <b>{voice_steadiness}</b>
            </span>
          )}
          {body_language_rating && (
            <span className="rounded-full bg-white px-3 py-1 text-xs text-navy/70 ring-1 ring-navy/10">
              On camera: <b>{body_language_rating}</b>
            </span>
          )}
        </div>
      )}
      {!!observations?.length && (
        <ul className="mt-2 space-y-1 text-sm text-navy/70">
          {observations.map((o, i) => (
            <li key={i}>• {o}</li>
          ))}
        </ul>
      )}
      {impact_on_communication && (
        <p className="mt-2 text-sm text-navy/60">{impact_on_communication}</p>
      )}
    </div>
  );
}

export function MockReview() {
  const { profileId = "", runId = "" } = useParams();
  const navigate = useNavigate();
  const [review, setReview] = useState<MockReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .mockReview(profileId, runId)
      .then((r) => active && setReview(r))
      .catch((e) => active && setError((e as Error).message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [profileId, runId]);

  if (loading) return <Spinner label="Loading your review…" />;

  if (error || !review) {
    return (
      <div className="card p-10 text-center">
        <p className="text-lg font-semibold">Couldn't load this review.</p>
        {error && (
          <div className="mx-auto mt-4 max-w-md">
            <ErrorNote message={error} />
          </div>
        )}
        <div className="mt-6 flex justify-center">
          <Button onClick={() => navigate(`/mock/history/${profileId}`)}>
            Back to past interviews
          </Button>
        </div>
      </div>
    );
  }

  const report = review.report ?? {};
  const target = [review.job_title, review.company].filter(Boolean).join(" · ");
  const turns = review.turns ?? [];

  // Follow-ups hang off the question they probed, so they don't take a number.
  let questionNumber = 0;
  const numberedTurns = turns.map((turn) => {
    if (!turn.is_follow_up) questionNumber += 1;
    return { turn, number: questionNumber };
  });

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Your interview review"
        subtitle={
          target
            ? `${target}${turns.length ? ` · ${turns.length} questions` : ""}`
            : "How you did in this mock interview."
        }
      />

      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          {report.readiness && (
            <span className="rounded-full bg-brand/10 px-4 py-1.5 text-sm font-semibold text-brand-600">
              Readiness: {report.readiness}
            </span>
          )}
          {typeof review.average_score === "number" && (
            <span className="rounded-full bg-navy px-4 py-1.5 font-mono text-sm text-white">
              Avg score {review.average_score.toFixed(1)}/5
            </span>
          )}
        </div>

        {report.overall_summary && (
          <div className="card p-6">
            <p className="text-navy/80">{report.overall_summary}</p>
            {report.focus_next && (
              <p className="mt-4 rounded-2xl bg-brand/5 px-4 py-3 text-sm font-medium text-brand-600">
                🎯 Focus next: {report.focus_next}
              </p>
            )}
          </div>
        )}

        <Section title="What you did well" items={report.top_strengths} tone="green" />
        <Section title="Areas to improve" items={report.areas_to_improve} tone="amber" />
        <Section title="Action items to practice" items={report.action_items} tone="brand" />

        {turns.length > 0 && (
          <div>
            <h2 className="mb-3 mt-8 text-xl font-bold">Question-by-question</h2>
            <div className="space-y-4">
              {numberedTurns.map(({ turn, number }, i) => (
                <QuestionCard key={i} turn={turn} number={number} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Button onClick={() => navigate("/mock")}>New mock interview</Button>
        <Button
          variant="subtle"
          onClick={() => navigate(`/mock/history/${profileId}`)}
        >
          Past interviews
        </Button>
        <Button variant="ghost" onClick={() => navigate("/profiles")}>
          Back to profiles
        </Button>
      </div>
    </div>
  );
}
