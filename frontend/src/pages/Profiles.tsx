import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Profile } from "../api/types";
import { Button, ErrorNote, PageHeader, Spinner, Tag } from "../components/ui";

export function Profiles() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  async function load() {
    setLoading(true);
    try {
      setProfiles(await api.listProfiles());
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

  async function remove(id: string) {
    if (!confirm(`Delete profile "${id}"?`)) return;
    await api.deleteProfile(id);
    load();
  }

  return (
    <div>
      <PageHeader
        title="Interview profiles"
        subtitle="Each profile combines a job description with one of your resume versions."
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="card p-8">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold">Saved profiles</h2>
            <p className="mt-1 text-sm text-navy/50">
              Select a profile to start practicing interview questions tailored
              to that job.
            </p>
          </div>
          <Button onClick={() => navigate("/profiles/new")}>+ Add new profile</Button>
        </div>

        <div className="mt-6 space-y-4">
          {loading ? (
            <Spinner label="Loading profiles…" />
          ) : profiles.length === 0 ? (
            <p className="text-navy/50">
              You don't have any profiles yet. Click <b>"+ Add new profile"</b> to
              create one using one of your resumes.
            </p>
          ) : (
            profiles.map((p) => {
              const open = expanded[p.profile_id];
              const jd = p.job_description || "";
              return (
                <div key={p.profile_id} className="rounded-3xl border border-navy/10 p-6">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-bold">
                        {p.job_title || p.profile_id}
                      </h3>
                      <p className="text-sm text-navy/50">{p.company || "—"}</p>
                    </div>
                    <Tag>{p.resume_version}</Tag>
                  </div>

                  <p className="mt-3 text-sm text-navy/70">
                    {open ? jd : jd.slice(0, 180)}
                    {jd.length > 180 && (
                      <button
                        className="ml-1 text-brand-600"
                        onClick={() =>
                          setExpanded((e) => ({ ...e, [p.profile_id]: !open }))
                        }
                      >
                        {open ? "See less" : "… See more"}
                      </button>
                    )}
                  </p>

                  <div className="mt-5 flex items-center justify-between">
                    <button
                      onClick={() => remove(p.profile_id)}
                      className="text-sm text-navy/40 hover:text-rose-500"
                    >
                      Delete profile
                    </button>
                    <div className="flex gap-2">
                      <Button
                        variant="subtle"
                        onClick={() => navigate(`/mock/history/${p.profile_id}`)}
                      >
                        Reviews
                      </Button>
                      <Button onClick={() => navigate(`/practice/${p.profile_id}`)}>
                        Practice
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
