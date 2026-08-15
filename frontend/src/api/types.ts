export interface ResumeSummary {
  id: string;
  full_name: string | null;
  headline: string | null;
}

export interface ResumeBulletItem {
  company?: string;
  job_title?: string;
  location?: string;
  start_date?: string;
  end_date?: string;
  is_current?: boolean;
  project_name?: string;
  bullets?: string[];
}

export interface EducationItem {
  degree?: string;
  field_of_study?: string;
  institution?: string;
  location?: string;
  start_date?: string;
  end_date?: string;
  gpa?: string;
  relevant_courses?: string[];
}

export interface ResumeSection {
  section_name: string;
  items: Record<string, unknown>[];
}

export interface ResumeDocument {
  document_type?: string;
  source?: { file_name?: string; page_count?: number };
  candidate?: { full_name?: string | null; headline?: string | null };
  sections: ResumeSection[];
}

export interface Profile {
  profile_id: string;
  job_title?: string | null;
  company?: string | null;
  resume_version: string;
  job_description: string;
  created_at?: string;
  updated_at?: string;
}

export interface GeneratedQuestion {
  id: string;
  question: string;
  competency?: string;
  technique?: string;
  difficulty?: string;
  expected_strong_answer_signals?: string[];
}

export interface GeneratedQuestions {
  questions: GeneratedQuestion[];
  coverage_summary?: Record<string, unknown>;
}

export interface CriterionScore {
  criterion: string;
  score: number;
  weight?: number;
  reason?: string;
  improvement_advice?: string;
  missing_evidence?: string[];
}

export interface Evaluation {
  overall_score?: number;
  overall_rating?: string;
  hiring_signal?: string;
  summary?: string;
  criteria_scores?: CriterionScore[];
  strengths?: string[];
  weaknesses?: string[];
  follow_up_questions?: string[];
  candidate_coaching?: {
    better_answer_strategy?: string;
    example_improvement?: string;
  };
  delivery_assessment?: {
    fluency_rating?: string;
    voice_steadiness?: string;
    body_language_rating?: string;
    observations?: string[];
    impact_on_communication?: string;
  };
}

export interface SuggestedBulletGroup {
  heading: string;
  bullets: string[];
}

export interface TranscribeResult {
  text: string;
  fluency?: Record<string, unknown> | null;
  voice?: Record<string, unknown> | null;
  video_presentation?: Record<string, unknown> | null;
  delivery_metrics?: Record<string, unknown> | null;
  recording_path?: string | null;
}

export interface PracticeRun {
  profile_id: string;
  question: string;
  answer: string;
  evaluation: Evaluation;
  created_at: string;
}

export interface ReportTurn {
  question: string;
  answer: string;
  overall_score?: number;
  hiring_signal?: string;
  summary?: string;
  strengths?: string[];
  weaknesses?: string[];
}

export interface MockQuestion {
  id?: string;
  question?: string;
  competency?: string;
  technique?: string;
  difficulty?: string;
  is_follow_up?: boolean;
}

export interface MockSession {
  thread_id: string;
  status: string;
  done: boolean;
  question_index: number;
  total_questions: number;
  question?: MockQuestion;
  report?: PracticeReport;
  run_id?: string;
}

export interface MockReviewTurn {
  question: string;
  answer: string;
  competency?: string;
  is_follow_up?: boolean;
  overall_score?: number;
  hiring_signal?: string;
  summary?: string;
  strengths?: string[];
  weaknesses?: string[];
  delivery_assessment?: Evaluation["delivery_assessment"];
}

export interface MockReviewSummary {
  run_id: string;
  profile_id: string;
  job_title?: string | null;
  company?: string | null;
  interviewer_role?: string | null;
  interviewer_style?: string | null;
  question_count?: number;
  average_score?: number | null;
  readiness?: string;
  created_at: string;
}

export interface MockReview extends MockReviewSummary {
  report: PracticeReport;
  turns: MockReviewTurn[];
}

export interface DashboardInterview {
  run_id: string;
  profile_id: string;
  job_title?: string | null;
  company?: string | null;
  interviewer_role?: string | null;
  interviewer_style?: string | null;
  created_at: string;
  average_score?: number | null;
  readiness?: string | null;
  question_count?: number;
}

export interface CompetencyStat {
  competency: string;
  avg_score: number;
  count: number;
}

export interface RoleStat {
  label: string;
  avg_score: number;
  count: number;
}

export interface DashboardProfileOption {
  profile_id: string;
  label: string;
}

export interface MockDashboard {
  totals: {
    interviews: number;
    questions: number;
    average_score: number | null;
    latest_readiness: string | null;
    recorded_answers: number;
  };
  interviews: DashboardInterview[];
  competencies: CompetencyStat[];
  by_role: RoleStat[];
  readiness_counts: Record<string, number>;
  delivery: Record<string, Record<string, number>>;
  profiles: DashboardProfileOption[];
  filters: { profile_id: string | null; days: number | null };
}

export interface MockStartOptions {
  profile_id: string;
  question_count?: number;
  difficulty?: string;
  interviewer_role?: string;
  interviewer_style?: string;
  extra_notes?: string;
}

export interface PracticeReport {
  overall_summary?: string;
  readiness?: string;
  top_strengths?: string[];
  areas_to_improve?: string[];
  action_items?: string[];
  focus_next?: string;
}
