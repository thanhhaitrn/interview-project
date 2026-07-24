import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SuggestedBulletGroup } from "../api/types";
import { Spinner } from "./ui";

export function AICoachPanel({
  resumeId,
  profileId,
  question,
}: {
  resumeId: string;
  profileId: string;
  question: string;
}) {
  const [groups, setGroups] = useState<SuggestedBulletGroup[]>([]);
  const [loadingBullets, setLoadingBullets] = useState(true);
  const [sample, setSample] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoadingBullets(true);
    api
      .suggestedBullets(resumeId, question)
      .then(setGroups)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoadingBullets(false));
  }, [resumeId, question]);

  // Reset the sample answer when the question changes.
  useEffect(() => {
    setSample("");
    setRevealed(false);
  }, [question]);

  async function generate() {
    setGenerating(true);
    setError("");
    try {
      const { sample_answer } = await api.sampleAnswer(profileId, question);
      setSample(sample_answer);
      setRevealed(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <aside className="space-y-5">
      <div className="card p-5">
        <h3 className="font-bold">📝 Suggested Bullets</h3>
        {loadingBullets ? (
          <div className="mt-3"><Spinner /></div>
        ) : groups.length === 0 ? (
          <p className="mt-2 text-sm text-navy/50">No resume bullets found.</p>
        ) : (
          <div className="mt-3 space-y-4">
            {groups.map((g, i) => (
              <div key={i}>
                <p className="text-xs font-bold uppercase tracking-wide text-navy/50">
                  {g.heading}
                </p>
                <ul className="mt-1 space-y-1">
                  {g.bullets.map((b, bi) => (
                    <li key={bi} className="flex gap-2 text-sm text-navy/70">
                      <input type="checkbox" className="mt-1 accent-brand" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card p-5">
        <h3 className="font-bold">✨ AI Sample Answer</h3>
        <div className="mt-2 flex gap-3 text-sm">
          <button
            onClick={generate}
            disabled={generating}
            className="font-medium text-brand-600 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate"}
          </button>
          {sample && (
            <button
              onClick={() => setRevealed((v) => !v)}
              className="font-medium text-navy/60"
            >
              {revealed ? "Hide" : "Reveal"}
            </button>
          )}
        </div>
        {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
        {sample && (
          <p
            className={`mt-3 whitespace-pre-line text-sm text-navy/80 transition ${
              revealed ? "" : "select-none blur-sm"
            }`}
          >
            {sample}
          </p>
        )}
        {!sample && !generating && (
          <p className="mt-2 text-sm text-navy/40">
            Uses your projects and experience to personalize your story.
          </p>
        )}
      </div>
    </aside>
  );
}
