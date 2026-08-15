import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DashboardInterview, MockDashboard } from "../api/types";
import { Button, ErrorNote, PageHeader, Segmented, Spinner } from "../components/ui";
import { Overview } from "./Dashboard";

const TIME_RANGES = [
  { label: "All time", value: 0 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

function formatDate(iso?: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function prettify(key?: string | null) {
  if (!key) return "";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function ReviewList({ items }: { items: DashboardInterview[] }) {
  if (!items.length) return <p className="text-sm text-navy/40">No interviews in this range.</p>;
  return (
    <div className="space-y-3">
      {items.map((r) => {
        const meta = [
          formatDate(r.created_at),
          [prettify(r.interviewer_role), prettify(r.interviewer_style)].filter(Boolean).join(" · "),
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
                {r.job_title || r.profile_id}
                {r.company ? ` — ${r.company}` : ""}
              </p>
              <p className="mt-1 text-sm text-navy/50">{meta || "Mock interview"}</p>
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
  );
}

/**
 * Past interviews = an Overview tab (dashboard charts) and a List tab (every
 * saved review), sharing one profile + time-range filter. Also mounted at
 * /dashboard and /mock/history/:profileId (the latter pre-selects that profile).
 */
export function MockHistory() {
  const { profileId: paramProfile } = useParams();
  const navigate = useNavigate();

  const [tab, setTab] = useState<"overview" | "list">("overview");
  const [profileId, setProfileId] = useState(paramProfile ?? "");
  const [days, setDays] = useState(0);

  const [data, setData] = useState<MockDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const first = data === null;
    if (first) setLoading(true);
    else setRefreshing(true);
    api
      .mockDashboard({ profile_id: profileId || undefined, days: days || undefined })
      .then((d) => active && (setData(d), setError("")))
      .catch((e) => active && setError((e as Error).message))
      .finally(() => {
        if (!active) return;
        setLoading(false);
        setRefreshing(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, days]);

  if (loading) return <Spinner label="Loading past interviews…" />;
  if (error && !data) return <div className="mb-4"><ErrorNote message={error} /></div>;
  if (!data) return null;

  const hasAnyData = data.profiles.length > 0;
  const filtersActive = !!profileId || days > 0;
  const list = [...data.interviews].reverse(); // newest first
  const resetFilters = () => {
    setProfileId("");
    setDays(0);
  };

  return (
    <div>
      <PageHeader title="Past interviews" subtitle="An overview of your performance and every saved review." />

      {/* Tabs + shared filters */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={tab}
          options={[
            { label: "Overview", value: "overview" },
            { label: "List", value: "list" },
          ]}
          onChange={setTab}
        />
        {hasAnyData && (
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="rounded-full border border-navy/15 bg-white px-4 py-1.5 text-sm"
            >
              <option value="">All profiles</option>
              {data.profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.label}
                </option>
              ))}
            </select>
            <Segmented value={days} options={TIME_RANGES} onChange={setDays} />
            {filtersActive && (
              <button onClick={resetFilters} className="text-sm text-navy/40 hover:text-navy">
                Reset
              </button>
            )}
            {refreshing && <span className="text-xs text-navy/40">updating…</span>}
          </div>
        )}
      </div>

      {data.totals.interviews === 0 ? (
        <div className="card p-10 text-center">
          {filtersActive ? (
            <>
              <p className="text-lg font-semibold">No interviews match these filters.</p>
              <div className="mt-6 flex justify-center">
                <Button variant="subtle" onClick={resetFilters}>
                  Reset filters
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-lg font-semibold">No interview data yet.</p>
              <p className="mt-2 text-navy/60">
                Finish a mock interview and your scores, trends, and reviews show up here.
              </p>
              <div className="mt-6 flex justify-center">
                <Button onClick={() => navigate("/mock")}>Start a mock interview</Button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className={refreshing ? "opacity-60 transition" : "transition"}>
          {tab === "overview" ? <Overview data={data} /> : <ReviewList items={list} />}
        </div>
      )}

      <div className="mt-8 flex gap-3">
        <Button onClick={() => navigate("/mock")}>New mock interview</Button>
        <Button variant="subtle" onClick={() => navigate("/profiles")}>
          Back to profiles
        </Button>
      </div>
    </div>
  );
}
