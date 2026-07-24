import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { MockSession, Profile } from "../api/types";
import { Button, ErrorNote, Spinner } from "../components/ui";
import { useSpeech } from "../hooks/useSpeech";

type LiveState = {
  session?: MockSession;
  profileId?: string;
  voiceURI?: string;
  coachingHints?: boolean;
  profile?: Profile;
};

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function MockLive() {
  const navigate = useNavigate();
  const state = (useLocation().state ?? {}) as LiveState;
  const { profileId = "", voiceURI, coachingHints = true, profile } = state;

  const { supported, speak, cancel, speaking } = useSpeech();

  const [session, setSession] = useState<MockSession | undefined>(state.session);
  const [started, setStarted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState("");
  const [answerSaved, setAnswerSaved] = useState(false);
  const [error, setError] = useState("");
  const [typed, setTyped] = useState("");
  const [showType, setShowType] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  const question = session?.question;
  const questionText = question?.question ?? "";

  // --- camera preview -------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    async function openCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      } catch {
        setError(
          "Could not access your camera/microphone. Check browser permissions."
        );
      }
    }
    openCamera();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (timerRef.current) window.clearInterval(timerRef.current);
      window.speechSynthesis?.cancel();
    };
  }, []);

  // --- per-question timer ---------------------------------------------------
  useEffect(() => {
    if (!started || session?.done) return;
    setElapsed(0);
    timerRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [started, session?.question?.id, session?.done]);

  // --- read the question out loud -------------------------------------------
  useEffect(() => {
    if (!started || !questionText || session?.done) return;
    speak(questionText, voiceURI);
  }, [started, questionText, session?.done, speak, voiceURI]);

  // --- finished -------------------------------------------------------------
  useEffect(() => {
    if (!session?.done) return;
    cancel();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    // Reviews are now saved server-side, so open the durable review by id.
    if (session.run_id) {
      navigate(`/mock/review/${profileId}/${session.run_id}`, { replace: true });
      return;
    }
    navigate(`/practice/${profileId}/report`, {
      state: {
        report: session.report,
        jobTitle: profile?.job_title,
        company: profile?.company,
        answered: session.total_questions,
        fromMock: true,
      },
      replace: true,
    });
  }, [session, navigate, profileId, profile, cancel]);

  const submitAnswer = useCallback(
    async (answer: string, source: string, delivery?: Record<string, unknown> | null) => {
      if (!session) return;
      setBusy("Evaluating your answer…");
      setError("");
      try {
        const next = await api.mockAnswer({
          thread_id: session.thread_id,
          answer,
          answer_source: source,
          delivery_metrics: delivery ?? null,
        });
        setAnswerSaved(true);
        setTyped("");
        setShowType(false);
        setSession(next);
        window.setTimeout(() => setAnswerSaved(false), 2500);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy("");
      }
    },
    [session]
  );

  function startRecording() {
    const stream = streamRef.current;
    if (!stream) return setError("Camera/microphone is not ready yet.");
    cancel(); // stop the interviewer voice before recording
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream, { audioBitsPerSecond: 128000 });
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
      setBusy("Transcribing your answer…");
      try {
        const result = await api.transcribe(blob, "mock_answer.webm");
        if (!result.text.trim()) {
          setError("Couldn't hear an answer — try recording again.");
          setBusy("");
          return;
        }
        await submitAnswer(result.text, "record_video", result.delivery_metrics);
      } catch (e) {
        setError((e as Error).message);
        setBusy("");
      }
    };
    recorder.start(1000);
    recorderRef.current = recorder;
    setRecording(true);
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  function endInterview() {
    if (!confirm("End this interview? You'll lose the remaining questions.")) return;
    cancel();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    navigate("/profiles");
  }

  if (!session) {
    return (
      <div className="card p-10 text-center">
        <p className="text-lg font-semibold">No interview in progress.</p>
        <p className="mt-2 text-navy/60">Set up a mock interview to begin.</p>
        <div className="mt-6 flex justify-center">
          <Button onClick={() => navigate("/mock")}>Go to setup</Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Question banner */}
      <div className="rounded-4xl bg-brand p-6 text-white shadow-lg">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full bg-white/20 px-3 py-1">
            {question?.competency || "Interview"}
            {question?.technique ? ` · ${question.technique}` : ""}
            {` · Q${session.question_index + 1}`}
          </span>
          {question?.is_follow_up && (
            <span className="rounded-full bg-amber-400/90 px-3 py-1 font-semibold text-navy">
              ↳ Follow-up
            </span>
          )}
          {session.total_questions > 0 && (
            <span className="text-white/70">
              of {session.total_questions} planned
            </span>
          )}
          {speaking && <span className="text-white/80">🔊 speaking…</span>}
        </div>
        <p className="mt-3 text-lg font-semibold leading-relaxed">
          {started
            ? questionText
            : "When you're ready, click Start interview. The interviewer will read each question out loud."}
        </p>
        {started && supported && (
          <button
            onClick={() => speak(questionText, voiceURI)}
            className="mt-3 rounded-full bg-white/15 px-4 py-1.5 text-sm hover:bg-white/25"
          >
            🔁 Repeat question
          </button>
        )}
      </div>

      {error && <div className="mt-4"><ErrorNote message={error} /></div>}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Camera + controls */}
        <div className="lg:col-span-2">
          <div className="relative overflow-hidden rounded-4xl bg-navy">
            <video
              ref={videoRef}
              muted
              playsInline
              className="aspect-video w-full object-cover"
            />
            {answerSaved && (
              <span className="absolute left-4 top-4 rounded-full bg-black/70 px-3 py-1 text-sm text-green-400">
                ● Answer saved
              </span>
            )}
            {recording && (
              <span className="absolute right-4 top-4 rounded-full bg-rose-600 px-3 py-1 text-sm text-white">
                ● Recording
              </span>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {!started ? (
              <Button onClick={() => setStarted(true)}>Start interview</Button>
            ) : recording ? (
              <Button variant="danger" onClick={stopRecording}>
                Stop & submit answer
              </Button>
            ) : (
              <Button onClick={startRecording} disabled={!!busy}>
                🎙 Record answer
              </Button>
            )}

            <Button variant="subtle" onClick={endInterview}>
              End interview
            </Button>

            {started && !busy && (
              <span className="rounded-full bg-navy px-4 py-1.5 font-mono text-sm text-white">
                Question time {formatTime(elapsed)}
              </span>
            )}
            {busy && <Spinner label={busy} />}
          </div>

          {started && !recording && !busy && (
            <div className="mt-4">
              {showType ? (
                <div>
                  <textarea
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    rows={4}
                    placeholder="Type your answer instead…"
                    className="w-full rounded-2xl border border-navy/15 px-4 py-3 text-sm"
                  />
                  <div className="mt-2 flex gap-2">
                    <Button
                      onClick={() => submitAnswer(typed, "text")}
                      disabled={!typed.trim()}
                    >
                      Submit answer
                    </Button>
                    <Button variant="ghost" onClick={() => setShowType(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowType(true)}
                  className="text-sm text-navy/50 hover:text-navy"
                >
                  Type my answer instead
                </button>
              )}
            </div>
          )}
        </div>

        {/* Coaching hints */}
        {coachingHints && (
          <aside className="card h-fit p-5">
            <h3 className="font-bold">💡 Coaching Hints</h3>
            <p className="mt-3 text-xs font-bold uppercase tracking-wide text-navy/40">
              Structure guide
            </p>
            <ul className="mt-2 space-y-2 text-sm text-navy/70">
              <li><b>Situation</b> — set the scene in one sentence.</li>
              <li><b>Task</b> — what you were responsible for.</li>
              <li><b>Action</b> — the specific steps you took.</li>
              <li><b>Result</b> — the outcome, with a number if you have one.</li>
            </ul>
            {question?.competency && (
              <p className="mt-4 rounded-2xl bg-brand/5 px-3 py-2 text-sm text-brand-600">
                They're assessing: <b>{question.competency}</b>
              </p>
            )}
            <p className="mt-4 text-xs text-navy/40">
              Aim for about 1–2 minutes per answer.
            </p>
          </aside>
        )}
      </div>
    </div>
  );
}
