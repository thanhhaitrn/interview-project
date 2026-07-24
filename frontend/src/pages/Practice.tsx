import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  Evaluation,
  GeneratedQuestion,
  Profile,
  ReportTurn,
} from "../api/types";
import { Button, ErrorNote, Spinner } from "../components/ui";
import { Recorder } from "../components/Recorder";
import { ScoreFeedback } from "../components/ScoreFeedback";
import { AICoachPanel } from "../components/AICoachPanel";

export function Practice() {
  const { profileId = "" } = useParams();
  const navigate = useNavigate();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [customQuestion, setCustomQuestion] = useState<string | null>(null);

  const [answer, setAnswer] = useState("");
  const [delivery, setDelivery] = useState<Record<string, unknown> | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);

  const [sessionTurns, setSessionTurns] = useState<ReportTurn[]>([]);
  const [finishing, setFinishing] = useState(false);

  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState("");
  const [showCoach, setShowCoach] = useState(false);
  const [showRecorder, setShowRecorder] = useState(false);

  const isLastQuestion = !customQuestion && index >= questions.length - 1;

  const currentQuestion = customQuestion ?? questions[index]?.question ?? "";

  useEffect(() => {
    async function init() {
      setLoading(true);
      try {
        const p = await api.getProfile(profileId);
        setProfile(p);
        const gen = await api.generateQuestions(profileId);
        setQuestions(gen.questions || []);
        setError("");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [profileId]);

  function resetForNext() {
    setAnswer("");
    setDelivery(null);
    setEvaluation(null);
    setCustomQuestion(null);
  }

  function nextQuestion() {
    resetForNext();
    setIndex((i) => Math.min(i + 1, Math.max(questions.length - 1, 0)));
  }

  async function evaluate() {
    if (!answer.trim()) return setError("Write or record an answer first.");
    setEvaluating(true);
    setError("");
    try {
      const result = await api.evaluate({
        profile_id: profileId,
        question: currentQuestion,
        answer,
        delivery_metrics: delivery,
      });
      setEvaluation(result);
      // Record/replace this question's turn for the end-of-session report.
      const turn: ReportTurn = {
        question: currentQuestion,
        answer,
        overall_score: result.overall_score,
        hiring_signal: result.hiring_signal,
        summary: result.summary,
        strengths: result.strengths,
        weaknesses: result.weaknesses,
      };
      setSessionTurns((prev) => {
        const without = prev.filter((t) => t.question !== currentQuestion);
        return [...without, turn];
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEvaluating(false);
    }
  }

  async function finishSession() {
    if (sessionTurns.length === 0)
      return setError("Answer at least one question before finishing.");
    setFinishing(true);
    setError("");
    try {
      const report = await api.report(profileId, sessionTurns);
      navigate(`/practice/${profileId}/report`, {
        state: {
          report,
          jobTitle: profile?.job_title,
          company: profile?.company,
          answered: sessionTurns.length,
        },
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setFinishing(false);
    }
  }

  async function handleRecorded(blob: Blob, filename: string) {
    setShowRecorder(false);
    setTranscribing(true);
    setError("");
    try {
      const res = await api.transcribe(blob, filename);
      setAnswer((prev) => (prev ? `${prev}\n${res.text}` : res.text));
      setDelivery(res.delivery_metrics ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTranscribing(false);
    }
  }

  function useOwnQuestion() {
    const q = prompt("Type your own question:");
    if (q && q.trim()) {
      resetForNext();
      setCustomQuestion(q.trim());
    }
  }

  if (loading) return <Spinner label="Generating tailored questions…" />;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/profiles")} className="text-navy/50">
            ←
          </button>
          <h1 className="text-2xl font-bold">
            {profile?.job_title || profile?.profile_id}
            {profile?.company ? `, ${profile.company}` : ""}
          </h1>
          <span className="rounded-full bg-navy/5 px-3 py-1 text-sm">
            Q{index + 1} · Ready
          </span>
        </div>
        <label className="flex items-center gap-2 text-sm text-navy/60">
          <input
            type="checkbox"
            checked={showCoach}
            onChange={(e) => setShowCoach(e.target.checked)}
            className="accent-brand"
          />
          Show AI Coach
        </label>
      </div>

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className={`grid gap-6 ${showCoach ? "lg:grid-cols-3" : ""}`}>
        <div className={showCoach ? "lg:col-span-2" : ""}>
          {/* Question card */}
          <div className="card p-6">
            <div className="flex items-center justify-between">
              <span className="rounded-full bg-brand/10 px-3 py-1 text-sm text-brand-600">
                {customQuestion ? "Your question" : "Auto (from JD)"}
              </span>
              <span className="rounded-full bg-navy/5 px-3 py-1 text-sm">
                Q{index + 1}
              </span>
            </div>
            <p className="mt-3 text-xs font-bold uppercase tracking-wide text-navy/40">
              Question
            </p>
            <p className="mt-1 text-lg">{currentQuestion || "No questions generated."}</p>
          </div>

          {/* Answer */}
          <div className="card mt-6 p-6">
            <p className="text-xs font-bold uppercase tracking-wide text-navy/40">
              Your answer
            </p>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={6}
              placeholder="Type your answer here. You can also record an audio/video answer."
              className="mt-2 w-full rounded-2xl border border-navy/15 px-4 py-3"
            />
            <div className="mt-3 flex items-center gap-3">
              <Button variant="subtle" onClick={() => setShowRecorder(true)}>
                🎥 Open recorder
              </Button>
              {transcribing && <Spinner label="Transcribing…" />}
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
              <button onClick={useOwnQuestion} className="text-sm text-navy/60">
                Use my own question
              </button>
              <Button onClick={evaluate} disabled={evaluating}>
                {evaluating ? "Scoring…" : "Save answer"}
              </Button>
              {!isLastQuestion && (
                <Button variant="subtle" onClick={nextQuestion}>
                  Next question
                </Button>
              )}
              {(isLastQuestion || sessionTurns.length > 0) && (
                <Button onClick={finishSession} disabled={finishing}>
                  {finishing ? "Generating report…" : "Finish & get report"}
                </Button>
              )}
            </div>
            <p className="mt-2 text-right text-xs text-navy/40">
              {sessionTurns.length} of {questions.length} answered
            </p>
          </div>

          {/* Evaluation */}
          {evaluation && (
            <div className="card mt-6 p-6">
              <h3 className="mb-3 font-bold">Coach feedback</h3>
              <ScoreFeedback evaluation={evaluation} />
            </div>
          )}
        </div>

        {showCoach && profile && (
          <AICoachPanel
            resumeId={profile.resume_version}
            profileId={profileId}
            question={currentQuestion}
          />
        )}
      </div>

      {showRecorder && (
        <Recorder
          onClose={() => setShowRecorder(false)}
          onRecorded={handleRecorded}
        />
      )}
    </div>
  );
}
