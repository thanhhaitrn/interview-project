import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ResumeSummary } from "../api/types";
import { Badge, Button, ErrorNote, PageHeader, Spinner } from "../components/ui";

const STEPS = ["Upload & parse", "Edit experience & education", "Practice tailored questions"];

export function ResumeList() {
  const navigate = useNavigate();
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const [profileId, setProfileId] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      setResumes(await api.listResumes());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!profileId.trim()) return setError("Give the resume a unique name.");
    if (!file) return setError("Choose a PDF file.");
    setUploading(true);
    setError("");
    try {
      const { id } = await api.uploadResume(profileId.trim(), file);
      setShowUpload(false);
      setProfileId("");
      await load();
      navigate(`/resume/${id}/edit`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: string) {
    if (!confirm(`Delete resume "${id}"?`)) return;
    await api.deleteResume(id);
    load();
  }

  return (
    <div>
      <PageHeader
        title="Resume setup"
        subtitle="Upload your resume, parse it into structured sections, and refine your experience before practicing interviews."
      />

      <div className="mb-8 flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <Badge key={s}>
            {i + 1} · {s}
          </Badge>
        ))}
      </div>

      {error && (
        <div className="mb-4">
          <ErrorNote message={error} />
        </div>
      )}

      <div className="card p-8">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold">Your Resumes</h2>
            <p className="mt-1 text-sm text-navy/50">
              Manage your resume versions. Edit entries or delete old versions.
            </p>
          </div>
          <Button onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? "Cancel" : "+ Add New Resume"}
          </Button>
        </div>

        {showUpload && (
          <div className="mt-6 rounded-3xl border border-navy/10 p-6">
            <h3 className="font-bold">1. Upload Resume</h3>
            <p className="mt-1 text-sm text-navy/50">
              Give this resume a name (e.g. <code>resume_DS</code>), then upload
              your PDF.
            </p>
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              <label className="text-sm">
                <span className="text-navy/60">Profile ID (Unique Name)</span>
                <input
                  value={profileId}
                  onChange={(e) => setProfileId(e.target.value)}
                  placeholder="e.g. resume_DS"
                  className="mt-1 w-full rounded-xl border border-navy/15 px-4 py-2.5"
                />
              </label>
              <label className="text-sm">
                <span className="text-navy/60">Resume PDF</span>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  className="mt-1 w-full rounded-xl border border-navy/15 px-4 py-2 file:mr-3 file:rounded-full file:border-0 file:bg-navy/5 file:px-3 file:py-1"
                />
              </label>
            </div>
            <div className="mt-5 flex justify-end">
              <Button onClick={handleUpload} disabled={uploading}>
                {uploading ? "Uploading…" : "Upload & Parse"}
              </Button>
            </div>
          </div>
        )}

        <div className="mt-6">
          {loading ? (
            <Spinner label="Loading resumes…" />
          ) : resumes.length === 0 ? (
            <p className="text-navy/50">No resumes found.</p>
          ) : (
            <ul className="divide-y divide-navy/5">
              {resumes.map((r) => (
                <li key={r.id} className="flex items-center justify-between py-4">
                  <div>
                    <p className="font-semibold">{r.full_name || r.id}</p>
                    <p className="text-sm text-navy/50">
                      {r.headline || "—"} · <code className="text-xs">{r.id}</code>
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="subtle"
                      onClick={() => navigate(`/resume/${r.id}/edit`)}
                    >
                      Edit
                    </Button>
                    <Button variant="ghost" onClick={() => remove(r.id)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
