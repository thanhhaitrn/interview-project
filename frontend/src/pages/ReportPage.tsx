import { useLocation, useNavigate, useParams } from "react-router-dom";
import type { PracticeReport } from "../api/types";
import { Button, PageHeader } from "../components/ui";

type ReportState = {
  report?: PracticeReport;
  jobTitle?: string;
  company?: string;
  answered?: number;
};

function Section({
  title,
  items,
  tone = "navy",
}: {
  title: string;
  items?: string[];
  tone?: "navy" | "green" | "amber" | "brand";
}) {
  if (!items?.length) return null;
  const dot =
    tone === "green"
      ? "bg-green-500"
      : tone === "amber"
      ? "bg-amber-500"
      : tone === "brand"
      ? "bg-brand"
      : "bg-navy/40";
  return (
    <div className="card p-6">
      <h3 className="font-bold">{title}</h3>
      <ul className="mt-3 space-y-2">
        {items.map((it, i) => (
          <li key={i} className="flex gap-3 text-navy/80">
            <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ReportPage() {
  const { profileId = "" } = useParams();
  const navigate = useNavigate();
  const state = (useLocation().state ?? {}) as ReportState;
  const report = state.report;

  if (!report) {
    return (
      <div className="card p-10 text-center">
        <p className="text-lg font-semibold">No report to show.</p>
        <p className="mt-2 text-navy/60">
          Finish a practice session to generate your improvement report.
        </p>
        <div className="mt-6 flex justify-center">
          <Button onClick={() => navigate(`/practice/${profileId}`)}>
            Back to practice
          </Button>
        </div>
      </div>
    );
  }

  const target = [state.jobTitle, state.company].filter(Boolean).join(" · ");

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Your improvement report"
        subtitle={
          target
            ? `${target}${state.answered ? ` · ${state.answered} questions answered` : ""}`
            : "How to get stronger before the real interview."
        }
      />

      <div className="space-y-5">
        {report.readiness && (
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-brand/10 px-4 py-1.5 text-sm font-semibold text-brand-600">
              Readiness: {report.readiness}
            </span>
          </div>
        )}

        {report.overall_summary && (
          <div className="card p-6">
            <p className="text-navy/80">{report.overall_summary}</p>
            {report.focus_next && (
              <p className="mt-4 rounded-2xl bg-brand/5 px-4 py-3 text-sm font-medium text-brand-600">
                🎯 Focus next: {report.focus_next}
              </p>
            )}
          </div>
        )}

        <Section title="What you did well" items={report.top_strengths} tone="green" />
        <Section title="Areas to improve" items={report.areas_to_improve} tone="amber" />
        <Section title="Action items to practice" items={report.action_items} tone="brand" />
      </div>

      <div className="mt-8 flex gap-3">
        <Button onClick={() => navigate(`/practice/${profileId}`)}>
          Practice again
        </Button>
        <Button variant="subtle" onClick={() => navigate("/profiles")}>
          Back to profiles
        </Button>
      </div>
    </div>
  );
}
