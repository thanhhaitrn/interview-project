import type {
  Evaluation,
  GeneratedQuestions,
  MockReview,
  MockReviewSummary,
  MockSession,
  MockStartOptions,
  PracticeReport,
  Profile,
  ReportTurn,
  ResumeDocument,
  ResumeSummary,
  SuggestedBulletGroup,
  PracticeRun,
  TranscribeResult,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  // Resumes
  listResumes: () => request<ResumeSummary[]>("/resumes"),
  getResume: (id: string) => request<ResumeDocument>(`/resumes/${id}`),
  uploadResume: (profileId: string, file: File) => {
    const form = new FormData();
    form.append("profile_id", profileId);
    form.append("file", file);
    return request<{ id: string; resume: ResumeDocument }>("/resumes", {
      method: "POST",
      body: form,
    });
  },
  saveResume: (id: string, resume: ResumeDocument) =>
    request<ResumeDocument>(`/resumes/${id}`, json("PUT", resume)),
  deleteResume: (id: string) =>
    request<{ status: string }>(`/resumes/${id}`, { method: "DELETE" }),

  // Profiles
  listProfiles: () => request<Profile[]>("/profiles"),
  getProfile: (id: string) => request<Profile>(`/profiles/${id}`),
  createProfile: (p: Omit<Profile, "created_at" | "updated_at">) =>
    request<Profile>("/profiles", json("POST", p)),
  deleteProfile: (id: string) =>
    request<{ status: string }>(`/profiles/${id}`, { method: "DELETE" }),

  // Practice
  generateQuestions: (profileId: string, questionCount?: number) =>
    request<GeneratedQuestions>(
      "/practice/questions",
      json("POST", { profile_id: profileId, question_count: questionCount })
    ),
  sampleAnswer: (profileId: string, question: string) =>
    request<{ sample_answer: string }>(
      "/practice/sample-answer",
      json("POST", { profile_id: profileId, question })
    ),
  suggestedBullets: (resumeId: string, question?: string) => {
    const q = new URLSearchParams({ resume_id: resumeId });
    if (question) q.set("question", question);
    return request<SuggestedBulletGroup[]>(`/practice/suggested-bullets?${q}`);
  },
  evaluate: (payload: {
    profile_id: string;
    question: string;
    answer: string;
    delivery_metrics?: Record<string, unknown> | null;
  }) => request<Evaluation>("/practice/evaluate", json("POST", payload)),
  practiceHistory: (profileId: string) =>
    request<PracticeRun[]>(`/practice/history/${profileId}`),
  report: (profileId: string, turns: ReportTurn[]) =>
    request<PracticeReport>(
      "/practice/report",
      json("POST", { profile_id: profileId, turns })
    ),

  // Mock interview
  mockOptions: () =>
    request<{ roles: Record<string, string>; styles: Record<string, string> }>(
      "/mock/options"
    ),
  mockStart: (options: MockStartOptions) =>
    request<MockSession>("/mock/start", json("POST", options)),
  mockAnswer: (payload: {
    thread_id: string;
    answer: string;
    answer_source?: string;
    delivery_metrics?: Record<string, unknown> | null;
  }) => request<MockSession>("/mock/answer", json("POST", payload)),
  allMockHistory: () => request<MockReviewSummary[]>("/mock/history"),
  mockHistory: (profileId: string) =>
    request<MockReviewSummary[]>(`/mock/history/${profileId}`),
  mockReview: (profileId: string, runId: string) =>
    request<MockReview>(`/mock/history/${profileId}/${runId}`),

  // Media
  transcribe: (blob: Blob, filename: string) => {
    const form = new FormData();
    form.append("file", blob, filename);
    return request<TranscribeResult>("/transcribe", {
      method: "POST",
      body: form,
    });
  },
};
