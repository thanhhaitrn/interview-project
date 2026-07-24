import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { MockReviewSummary, Profile } from "../api/types";
import { Button, ErrorNote, PageHeader, Spinner } from "../components/ui";

function formatDate(iso?: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function prettify(key?: string | null) {
  if (!key) return "";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Past mock interviews. Mounted twice:
 *  - /reviews                     -> every review, across all profiles
 *  - /mock/history/:profileId     -> just that profile's reviews
 */
export function MockHistory() {
  const { profileId } = useParams();
  const navigate = useNavigate();
  const showingAll = !profileId;

  const [reviews, setReviews] = useState<MockReviewSummary[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);

    const load = profileId
      ? Promise.all([
          api.mockHistory(profileId),
          api.getProfile(profileId).catch(() => null),
        ])
      : api.allMockHistory().then((list) => [list, null] as const);

    load
      .then(([list, prof]) => {
        if (!active) return;
        setReviews(list);
        setProfile(prof);
        setError("");
      })
      .catch((e) => active && setError((e as Error).message))
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
  }, [profileId]);

  const target = profile
    ? [profile.job_title, profile.company].filter(Boolean).join(" · ")
    : "";

  if (loading) return <Spinner label="Loading past interviews…" />;

  return (
    <div>
      <PageHeader
        title="Past interviews"
        subtitle={
          showingAll
            ? "Every mock interview you've completed. Open one to see the full review."
            : target || "Saved reviews for this profile."
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="card p-8">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">
            {showingAll ? "All reviews" : "Reviews"}
          </h2>
          <Button onClick={() => navigate("/mock")}>New mock interview</Button>
        </div>

        {reviews.length === 0 ? (
          <p className="mt-6 text-navy/50">
            No mock interviews yet. Finish a realistic mock interview and your
            review will show up here.
          </p>
        ) : (
          <div className="mt-6 space-y-3">
            {reviews.map((r) => {
              const persona = [
                prettify(r.interviewer_role),
                prettify(r.interviewer_style),
              ]
                .filter(Boolean)
                .join(" · ");
              const meta = [
                showingAll ? formatDate(r.created_at) : "",
                persona,
                r.question_count ? `${r.question_count} questions` : "",
              ]
                .filter(Boolean)
                .join(" · ");

              return (
                <Link
                  key={`${r.profile_id}/${r.run_id}`}
                  to={`/mock/review/${r.profile_id}/${r.run_id}`}
                  className="flex items-center justify-between gap-4 rounded-3xl border border-navy/10 p-5 transition hover:bg-navy/5"
                >
                  <div>
                    <p className="font-semibold">
                      {showingAll
                        ? `${r.job_title || r.profile_id}${
                            r.company ? ` — ${r.company}` : ""
                          }`
                        : formatDate(r.created_at)}
                    </p>
                    <p className="mt-1 text-sm text-navy/50">
                      {meta || "Mock interview"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {r.readiness && (
                      <span className="rounded-full bg-brand/10 px-3 py-1 text-xs font-semibold text-brand-600">
                        {r.readiness}
                      </span>
                    )}
                    {typeof r.average_score === "number" && (
                      <span className="rounded-full bg-navy px-3 py-1 font-mono text-xs text-white">
                        {r.average_score.toFixed(1)}/5
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-6 flex gap-3">
        {!showingAll && (
          <Button variant="subtle" onClick={() => navigate("/reviews")}>
            All past interviews
          </Button>
        )}
        <Button variant="ghost" onClick={() => navigate("/profiles")}>
          Back to profiles
        </Button>
      </div>
    </div>
  );
}
