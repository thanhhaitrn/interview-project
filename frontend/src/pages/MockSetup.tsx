import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Profile } from "../api/types";
import { Button, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useSpeech } from "../hooks/useSpeech";

type Mode = "practice" | "realistic";

export function MockSetup() {
  const navigate = useNavigate();
  const { supported, voices } = useSpeech();

  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [styles, setStyles] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState<Mode>("realistic");
  const [voiceURI, setVoiceURI] = useState("");
  const [role, setRole] = useState("hiring_manager");
  const [style, setStyle] = useState("balanced");
  const [notes, setNotes] = useState("");
  const [questionCount, setQuestionCount] = useState(4);
  const [coachingHints, setCoachingHints] = useState(true);

  useEffect(() => {
    Promise.all([api.listProfiles(), api.mockOptions()])
      .then(([p, o]) => {
        setProfiles(p);
        setRoles(o.roles);
        setStyles(o.styles);
        if (p.length) setProfileId(p[0].profile_id);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const selected = profiles.find((p) => p.profile_id === profileId);

  async function start() {
    if (!profileId) return setError("Pick a job profile first.");
    if (mode === "practice") return navigate(`/practice/${profileId}`);

    setStarting(true);
    setError("");
    try {
      const session = await api.mockStart({
        profile_id: profileId,
        question_count: questionCount,
        interviewer_role: role,
        interviewer_style: style,
        extra_notes: notes || undefined,
      });
      navigate("/mock/live", {
        state: { session, profileId, voiceURI, coachingHints, profile: selected },
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  const field = "mt-1 w-full rounded-xl border border-navy/15 px-4 py-2.5 text-sm";

  if (loading) return <Spinner label="Loading profiles…" />;

  return (
    <div>
      <PageHeader
        title="Mock interview setup"
        subtitle="Choose a job profile, then decide how you want this mock interview to run."
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="card p-8">
        <h2 className="text-xl font-bold">Session settings</h2>
        <p className="mt-1 text-sm text-navy/50">
          Pick a job profile, then either jump into practice mode or set up a
          realistic timed mock interview.
        </p>

        {profiles.length === 0 ? (
          <div className="mt-6">
            <p className="text-navy/60">
              You need an interview profile first.
            </p>
            <Button className="mt-3" onClick={() => navigate("/profiles/new")}>
              Create a profile
            </Button>
          </div>
        ) : (
          <>
            <label className="mt-6 block text-sm">
              <span className="text-navy/60">Job profile</span>
              <select
                className={field}
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p.profile_id} value={p.profile_id}>
                    {p.job_title || p.profile_id}
                    {p.company ? ` — ${p.company}` : ""}
                  </option>
                ))}
              </select>
              {selected && (
                <span className="mt-1 block text-xs text-navy/40">
                  Uses resume <code>{selected.resume_version}</code>.
                </span>
              )}
            </label>

            {profileId && (
              <button
                type="button"
                onClick={() => navigate(`/mock/history/${profileId}`)}
                className="mt-3 text-sm font-medium text-brand-600 hover:text-brand-500"
              >
                📄 View past interviews for this profile
              </button>
            )}

            <p className="mt-6 text-sm text-navy/60">Interview style</p>
            <div className="mt-2 grid gap-3 md:grid-cols-2">
              {(
                [
                  ["practice", "Practice mode", "Answer questions at your own pace, with AI coaching."],
                  ["realistic", "Realistic mode", "Questions are asked out loud, one by one, on camera."],
                ] as const
              ).map(([value, title, desc]) => (
                <button
                  key={value}
                  onClick={() => setMode(value)}
                  className={`rounded-2xl border p-4 text-left transition ${
                    mode === value
                      ? "border-brand bg-brand/5"
                      : "border-navy/10 hover:bg-navy/5"
                  }`}
                >
                  <span className="font-semibold">{title}</span>
                  <span className="mt-1 block text-sm text-navy/50">{desc}</span>
                </button>
              ))}
            </div>

            {mode === "realistic" && (
              <div className="mt-6 border-t border-navy/10 pt-6">
                <div className="grid gap-5 md:grid-cols-2">
                  <label className="text-sm">
                    <span className="text-navy/60">Interviewer voice</span>
                    <select
                      className={field}
                      value={voiceURI}
                      onChange={(e) => setVoiceURI(e.target.value)}
                      disabled={!supported}
                    >
                      <option value="">Auto (browser default)</option>
                      {voices.map((v) => (
                        <option key={v.voiceURI} value={v.voiceURI}>
                          {v.name} ({v.lang})
                        </option>
                      ))}
                    </select>
                    <span className="mt-1 block text-xs text-navy/40">
                      {supported
                        ? "Only affects the spoken voice, not the questions."
                        : "This browser doesn't support speech synthesis."}
                    </span>
                  </label>

                  <label className="text-sm">
                    <span className="text-navy/60">Interviewer role</span>
                    <select
                      className={field}
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      {Object.entries(roles).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="text-sm">
                    <span className="text-navy/60">Interviewer style</span>
                    <select
                      className={field}
                      value={style}
                      onChange={(e) => setStyle(e.target.value)}
                    >
                      {Object.entries(styles).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="text-sm">
                    <span className="text-navy/60">Session length</span>
                    <select
                      className={field}
                      value={questionCount}
                      onChange={(e) => setQuestionCount(Number(e.target.value))}
                    >
                      {[3, 4, 5, 6, 8].map((n) => (
                        <option key={n} value={n}>
                          {n} questions
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="mt-5 block text-sm">
                  <span className="text-navy/60">Extra notes (optional)</span>
                  <textarea
                    className={field}
                    rows={2}
                    placeholder="Anything else about the interviewer (pace, focus areas, etc.)."
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </label>

                <label className="mt-5 flex items-center gap-2 text-sm text-navy/60">
                  <input
                    type="checkbox"
                    className="accent-brand"
                    checked={coachingHints}
                    onChange={(e) => setCoachingHints(e.target.checked)}
                  />
                  Show coaching hints (structure guide) during the interview
                </label>
              </div>
            )}

            <div className="mt-8 flex justify-end gap-3">
              <Button variant="subtle" onClick={() => navigate("/profiles")}>
                Cancel
              </Button>
              <Button onClick={start} disabled={starting}>
                {starting ? "Preparing questions…" : "Start"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
