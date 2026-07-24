import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ResumeSummary } from "../api/types";
import { Button, ErrorNote, PageHeader } from "../components/ui";

export function ProfileNew() {
  const navigate = useNavigate();
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    profile_id: "",
    job_title: "",
    company: "",
    resume_version: "",
    job_description: "",
  });

  useEffect(() => {
    api.listResumes().then(setResumes).catch((e) => setError((e as Error).message));
  }, []);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save() {
    if (!form.profile_id.trim()) return setError("Profile ID is required.");
    if (!form.resume_version) return setError("Pick a resume version.");
    if (!form.job_description.trim()) return setError("Paste the job description.");
    setSaving(true);
    setError("");
    try {
      await api.createProfile(form);
      navigate("/profiles");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const input = "mt-1 w-full rounded-xl border border-navy/15 px-4 py-2.5 text-sm";

  return (
    <div>
      <PageHeader
        title="New interview profile"
        subtitle="Link a job description to one of your resume versions. You can reuse the same resume across multiple jobs."
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="card p-8">
        <h2 className="text-xl font-bold">Profile details</h2>
        <p className="mt-1 text-sm text-navy/50">
          Give this profile a memorable ID, pick a resume version, and paste the
          full job description.
        </p>

        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <label className="text-sm">
            <span className="text-navy/60">Profile ID</span>
            <input
              className={input}
              placeholder="e.g. lyft_ds"
              value={form.profile_id}
              onChange={(e) => set("profile_id", e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="text-navy/60">Job title</span>
            <input
              className={input}
              placeholder="e.g. Data Science Intern"
              value={form.job_title}
              onChange={(e) => set("job_title", e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="text-navy/60">Company</span>
            <input
              className={input}
              placeholder="e.g. Lyft"
              value={form.company}
              onChange={(e) => set("company", e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="text-navy/60">Resume version</span>
            <select
              className={input}
              value={form.resume_version}
              onChange={(e) => set("resume_version", e.target.value)}
            >
              <option value="">Select a resume version</option>
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} {r.full_name ? `— ${r.full_name}` : ""}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-navy/40">
              Need another resume version?{" "}
              <Link to="/resume" className="text-brand-600">
                Go to Resume setup
              </Link>{" "}
              and come back.
            </span>
          </label>
        </div>

        <label className="mt-5 block text-sm">
          <span className="text-navy/60">Job description</span>
          <textarea
            className={`${input} font-mono`}
            rows={10}
            placeholder="Paste the full job description here…"
            value={form.job_description}
            onChange={(e) => set("job_description", e.target.value)}
          />
        </label>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="subtle" onClick={() => navigate("/profiles")}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save profile"}
          </Button>
        </div>
      </div>
    </div>
  );
}
