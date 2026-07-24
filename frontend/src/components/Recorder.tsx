import { useEffect, useRef, useState } from "react";
import { Button } from "./ui";

type Mode = "audio" | "video";

export function Recorder({
  onClose,
  onRecorded,
}: {
  onClose: () => void;
  onRecorded: (blob: Blob, filename: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("audio");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  function stopStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (timerRef.current) window.clearInterval(timerRef.current);
  }

  useEffect(() => () => stopStream(), []);

  async function start() {
    setError("");
    chunksRef.current = [];
    try {
      const audio: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      };
      const stream = await navigator.mediaDevices.getUserMedia(
        mode === "video" ? { audio, video: true } : { audio }
      );
      streamRef.current = stream;
      if (mode === "video" && videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      const recorder = new MediaRecorder(stream, { audioBitsPerSecond: 128000 });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        const ext = recorder.mimeType.includes("webm") ? "webm" : "dat";
        onRecorded(blob, `answer.${ext}`);
        stopStream();
      };
      // Flush a chunk every second so the full recording (incl. the tail) is
      // captured even if the browser would otherwise drop the last segment.
      recorder.start(1000);
      recorderRef.current = recorder;
      setRecording(true);
      setSeconds(0);
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch (e) {
      setError((e as Error).message || "Could not access microphone/camera.");
    }
  }

  function stop() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card w-full max-w-lg p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">Record your answer</h3>
          <button onClick={onClose} className="text-navy/40 hover:text-navy">
            ✕
          </button>
        </div>

        <div className="mt-4 flex gap-2">
          {(["audio", "video"] as Mode[]).map((m) => (
            <button
              key={m}
              disabled={recording}
              onClick={() => setMode(m)}
              className={`pill ${mode === m ? "bg-navy text-white" : "bg-navy/5"}`}
            >
              {m === "audio" ? "🎙 Audio" : "🎥 Video"}
            </button>
          ))}
        </div>

        {mode === "video" && (
          <video
            ref={videoRef}
            muted
            className="mt-4 aspect-video w-full rounded-2xl bg-navy/90 object-cover"
          />
        )}

        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}

        <div className="mt-5 flex items-center justify-between">
          <span className="font-mono text-sm text-navy/60">
            {recording ? `● ${seconds}s` : "Ready"}
          </span>
          {recording ? (
            <Button variant="danger" onClick={stop}>
              Stop & transcribe
            </Button>
          ) : (
            <Button onClick={start}>Start recording</Button>
          )}
        </div>
        <p className="mt-3 text-xs text-navy/40">
          Your recording is transcribed locally on the server; only the text and
          delivery metrics are returned.
        </p>
      </div>
    </div>
  );
}
