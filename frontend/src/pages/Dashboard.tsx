import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MockDashboard } from "../api/types";
import { Segmented } from "../components/ui";

// Reference chart chrome (light surface) — neutral inks so the marks carry color.
const INK = { text: "#52514e", muted: "#898781", grid: "#e1e0d9", axis: "#c3c2b7" };
const BRAND = "#0d9488";

// Continuous score -> color ramp (red low → amber mid → green high) so bars are
// distinguishable by shade even when scores cluster, not just three flat bands.
const SCORE_STOPS: [number, [number, number, number]][] = [
  [0, [220, 38, 38]], // #dc2626 red
  [2, [249, 115, 22]], // #f97316 orange
  [3, [245, 158, 11]], // #f59e0b amber
  [4, [132, 204, 22]], // #84cc16 lime
  [5, [22, 163, 74]], // #16a34a green
];

function scoreColor(score?: number | null): string {
  if (typeof score !== "number") return INK.muted;
  const s = Math.max(0, Math.min(5, score));
  let lo = SCORE_STOPS[0];
  let hi = SCORE_STOPS[SCORE_STOPS.length - 1];
  for (let i = 0; i < SCORE_STOPS.length - 1; i++) {
    if (s >= SCORE_STOPS[i][0] && s <= SCORE_STOPS[i + 1][0]) {
      lo = SCORE_STOPS[i];
      hi = SCORE_STOPS[i + 1];
      break;
    }
  }
  const t = hi[0] === lo[0] ? 0 : (s - lo[0]) / (hi[0] - lo[0]);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${mix(lo[1][0], hi[1][0])}, ${mix(lo[1][1], hi[1][1])}, ${mix(lo[1][2], hi[1][2])})`;
}

// Normalize the model's free-text delivery ratings into one plain 3-level scale.
type Bucket = "strong" | "okay" | "weak";
const BUCKETS: { key: Bucket; label: string; color: string }[] = [
  { key: "strong", label: "Strong", color: "#16a34a" },
  { key: "okay", label: "Okay", color: "#f59e0b" },
  { key: "weak", label: "Needs work", color: "#f43f5e" },
];

function deliveryBucket(label: string): Bucket {
  // Judge only the leading verdict (before the first dash/colon/paren) so
  // incidental words in a sentence-form rating don't flip the bucket.
  const head = label.toLowerCase().split(/[–—:(,-]/)[0].trim();
  if (/(strong|steady|good|clear|confiden|fluent|calm)/.test(head)) return "strong";
  if (/(fair|mild|moderate|medium|okay|\bok\b|some|adequate)/.test(head)) return "okay";
  if (/(weak|shaky|unstable|poor|low|nervous|halt|monoton|below|limited|lacking)/.test(head)) return "weak";
  return "okay";
}

function summarizeDelivery(dist: Record<string, number>) {
  const counts: Record<Bucket, number> = { strong: 0, okay: 0, weak: 0 };
  let total = 0;
  for (const [label, n] of Object.entries(dist)) {
    counts[deliveryBucket(label)] += n;
    total += n;
  }
  const score = total ? Math.round(((counts.strong + counts.okay * 0.5) / total) * 100) : 0;
  const verdict = score >= 70 ? "Mostly strong" : score >= 40 ? "Mixed" : "Needs work";
  const color = score >= 70 ? "#16a34a" : score >= 40 ? "#f59e0b" : "#f43f5e";
  return { counts, total, score, verdict, color };
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ticksFor(max: number): number[] {
  if (max <= 0) return [0];
  if (max <= 8) return Array.from({ length: Math.ceil(max) + 1 }, (_, i) => i);
  return [0, 1, 2, 3, 4].map((i) => Math.round((max / 4) * i));
}

function ScaleLegend() {
  return (
    <div className="flex items-center gap-1.5 text-[10px] font-medium text-navy/40">
      <span>0</span>
      <span
        className="h-2 w-16 rounded-full"
        style={{ background: "linear-gradient(to right, #dc2626, #f97316, #f59e0b, #84cc16, #16a34a)" }}
      />
      <span>5</span>
    </div>
  );
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-5">
      <p className="text-xs font-bold uppercase tracking-wide text-navy/40">{label}</p>
      <p className="mt-1 text-3xl font-extrabold tracking-tight text-navy">{value}</p>
      {sub && <p className="mt-1 text-sm text-navy/50">{sub}</p>}
    </div>
  );
}

// --- Interactive line chart (hover crosshair + tooltip, click to drill in) ---

type TrendPoint = {
  value: number;
  date?: string | null;
  label: string;
  runId?: string;
  profileId?: string;
};

function TrendChart({
  points,
  max,
  format,
  onSelect,
}: {
  points: TrendPoint[];
  max: number;
  format: (v: number) => string;
  onSelect: (p: TrendPoint) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const W = 720;
  const H = 260;
  const pad = { l: 34, r: 18, t: 16, b: 26 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const n = points.length;
  const domainMax = max <= 0 ? 1 : max;

  const x = (i: number) => (n > 1 ? pad.l + (i / (n - 1)) * plotW : pad.l + plotW / 2);
  const y = (v: number) => pad.t + (1 - v / domainMax) * plotH;

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
  const area = n > 1 ? `${line} L ${x(n - 1)} ${y(0)} L ${x(0)} ${y(0)} Z` : "";

  function idxFromEvent(e: React.MouseEvent): number | null {
    const svg = svgRef.current;
    if (!svg || n === 0) return null;
    const rect = svg.getBoundingClientRect();
    const vb = ((e.clientX - rect.left) / rect.width) * W;
    const ratio = n > 1 ? (vb - pad.l) / plotW : 0;
    return Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))));
  }

  const ticks = ticksFor(domainMax);
  const tickIdx = n <= 1 ? [0] : [...new Set([0, Math.floor((n - 1) / 2), n - 1])];
  const active = hover != null ? points[hover] : null;
  const clickable = !!active?.runId;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ cursor: clickable ? "pointer" : "default" }}
        role="img"
        aria-label="Interview metric over time"
        onMouseMove={(e) => setHover(idxFromEvent(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          const i = idxFromEvent(e);
          if (i != null && points[i]?.runId) onSelect(points[i]);
        }}
      >
        {ticks.map((g) => (
          <g key={g}>
            <line x1={pad.l} x2={W - pad.r} y1={y(g)} y2={y(g)} stroke={INK.grid} strokeWidth={1} />
            <text x={pad.l - 6} y={y(g) + 3} textAnchor="end" fontSize={10} fill={INK.muted}>
              {g}
            </text>
          </g>
        ))}

        {area && <path d={area} fill={BRAND} opacity={0.08} />}
        {n > 1 && (
          <path d={line} fill="none" stroke={BRAND} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        )}

        {hover != null && (
          <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + plotH} stroke={INK.axis} strokeWidth={1} strokeDasharray="3 3" />
        )}

        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 5 : 3.5} fill={BRAND} stroke="#ffffff" strokeWidth={1.5} />
        ))}

        {tickIdx.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize={10} fill={INK.muted}>
            {fmtDate(points[i]?.date)}
          </text>
        ))}
      </svg>

      {active && hover != null && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded-xl bg-navy px-3 py-2 text-xs text-white shadow-lg"
          style={{ left: `${(x(hover) / W) * 100}%`, top: 0 }}
        >
          <div className="font-semibold">{format(active.value)}</div>
          <div className="text-white/60">{fmtDate(active.date)}</div>
          <div className="max-w-[10rem] truncate text-white/60">{active.label}</div>
          {clickable && <div className="mt-0.5 text-white/40">Click to open review →</div>}
        </div>
      )}
    </div>
  );
}

function BarList({
  items,
  emptyLabel,
}: {
  items: { label: string; score: number; count: number }[];
  emptyLabel: string;
}) {
  if (!items.length) return <p className="text-sm text-navy/40">{emptyLabel}</p>;
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <div key={i} title={`${it.count} question${it.count === 1 ? "" : "s"}`}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate text-navy/80">{it.label}</span>
            <span className="shrink-0 font-mono text-xs tabular-nums text-navy/50">{it.score.toFixed(1)}/5</span>
          </div>
          <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-navy/5">
            <div className="h-full rounded-full" style={{ width: `${(it.score / 5) * 100}%`, background: scoreColor(it.score) }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function DeliveryMetric({ name, dist }: { name: string; dist: Record<string, number> }) {
  const { counts, total, score, verdict, color } = summarizeDelivery(dist);
  if (!total) return null;
  return (
    <div title={`${score}% strength across ${total} answer${total === 1 ? "" : "s"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm text-navy/80">{name}</p>
        <p className="text-xs font-semibold" style={{ color }}>{verdict}</p>
      </div>
      <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-navy/5">
        <div className="h-full rounded-full" style={{ width: `${score}%`, background: color }} />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-navy/50">
        {BUCKETS.filter((b) => counts[b.key] > 0).map((b) => (
          <span key={b.key} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: b.color }} />
            {b.label} · {counts[b.key]}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Presentational analytics view. Receives already-filtered dashboard data and
 * renders the stat tiles + charts. Filtering, fetching, tabs, and empty states
 * are owned by the page that embeds this.
 */
export function Overview({ data }: { data: MockDashboard }) {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<"score" | "questions">("score");
  const { totals, interviews, competencies, by_role, delivery } = data;

  const trend: TrendPoint[] = interviews
    .filter((it) => (metric === "score" ? typeof it.average_score === "number" : true))
    .map((it) => ({
      value: metric === "score" ? (it.average_score as number) : it.question_count ?? 0,
      date: it.created_at,
      label: [it.job_title, it.company].filter(Boolean).join(" · ") || "Mock interview",
      runId: it.run_id,
      profileId: it.profile_id,
    }));
  const trendMax = metric === "score" ? 5 : Math.max(1, ...trend.map((p) => p.value));

  const competencyBars = competencies.map((c) => ({ label: c.competency, score: c.avg_score, count: c.count }));
  const strengths = competencyBars.slice(0, 5);
  const focus = [...competencyBars].reverse().slice(0, 5);

  const deliveryMetrics = (
    [
      ["On-camera body language", delivery.body_language_rating || {}],
      ["Speaking fluency", delivery.fluency_rating || {}],
      ["Voice steadiness", delivery.voice_steadiness || {}],
    ] as [string, Record<string, number>][]
  ).filter(([, d]) => Object.keys(d).length > 0);

  return (
    <div>
      {/* Headline numbers */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Interviews" value={String(totals.interviews)} />
        <StatTile label="Questions answered" value={String(totals.questions)} />
        <StatTile
          label="Average score"
          value={totals.average_score != null ? `${totals.average_score.toFixed(1)}/5` : "—"}
        />
        <StatTile label="Latest readiness" value={totals.latest_readiness || "—"} />
      </div>

      {/* Trend with metric toggle */}
      <div className="mt-6 card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-bold">
            {metric === "score" ? "Average score over time" : "Questions per interview"}
          </h2>
          <Segmented
            value={metric}
            options={[
              { label: "Score", value: "score" },
              { label: "Questions", value: "questions" },
            ]}
            onChange={setMetric}
          />
        </div>
        {trend.length > 0 ? (
          <div className="mt-4">
            <TrendChart
              points={trend}
              max={trendMax}
              format={(v) => (metric === "score" ? `${v.toFixed(1)}/5` : `${v} questions`)}
              onSelect={(p) => p.runId && navigate(`/mock/review/${p.profileId}/${p.runId}`)}
            />
            <p className="mt-2 text-xs text-navy/40">Click a point to open that interview's review.</p>
          </div>
        ) : (
          <p className="mt-4 text-sm text-navy/40">No scored interviews in this range.</p>
        )}
      </div>

      {/* Strengths & focus areas */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-bold">Strongest competencies</h2>
            <ScaleLegend />
          </div>
          <p className="mt-1 text-xs text-navy/40">Average score per competency across all answers.</p>
          <div className="mt-4">
            <BarList items={strengths} emptyLabel="No competency data yet." />
          </div>
        </div>
        <div className="card p-6">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-bold">Focus areas</h2>
            <ScaleLegend />
          </div>
          <p className="mt-1 text-xs text-navy/40">Lowest-scoring competencies to work on next.</p>
          <div className="mt-4">
            <BarList items={focus} emptyLabel="No competency data yet." />
          </div>
        </div>
      </div>

      {/* By role + delivery */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {by_role.length > 1 && (
          <div className="card p-6">
            <h2 className="font-bold">By job profile</h2>
            <p className="mt-1 text-xs text-navy/40">Average interview score per role.</p>
            <div className="mt-4">
              <BarList
                items={by_role.map((r) => ({ label: r.label, score: r.avg_score, count: r.count }))}
                emptyLabel="No role data yet."
              />
            </div>
          </div>
        )}

        {deliveryMetrics.length > 0 && (
          <div className="card p-6">
            <h2 className="font-bold">🎥 On-camera delivery</h2>
            <p className="mt-1 text-xs text-navy/40">
              How you came across in {totals.recorded_answers} recorded answer
              {totals.recorded_answers === 1 ? "" : "s"} — a fuller bar means stronger delivery.
            </p>
            <div className="mt-4 space-y-4">
              {deliveryMetrics.map(([name, dist]) => (
                <DeliveryMetric key={name} name={name} dist={dist} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
