"""Structured output models for interview agent responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


EMPTY_TEXT_VALUES = {"", "null", "none", "n/a", "not applicable"}


def _is_empty_output_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in EMPTY_TEXT_VALUES
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def clean_empty_fields(value: Any) -> Any:
    """Remove empty fields from nested model/dict/list output payloads."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            cleaned_item = clean_empty_fields(item)
            if not _is_empty_output_value(cleaned_item):
                cleaned[key] = cleaned_item
        return cleaned

    if isinstance(value, list):
        cleaned_items = [
            clean_empty_fields(item)
            for item in value
        ]
        return [
            item
            for item in cleaned_items
            if not _is_empty_output_value(item)
        ]

    if isinstance(value, str):
        return value.strip()

    return value


class QuestionScoringGuidance(BaseModel):
    strong_answer: str = Field(description="Signals of a strong answer.")
    average_answer: str = Field(description="Signals of an average answer.")
    weak_answer: str = Field(description="Signals of a weak answer.")


class InterviewQuestionOutput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(default="", description="Stable question id, for example q1.")
    question: str = Field(
        default="",
        validation_alias=AliasChoices("question", "question_text"),
        description="The interview question to ask.",
    )
    competency: str = Field(default="", description="Primary competency being assessed.")
    technique: str = Field(default="", description="Interview technique used for the question.")
    difficulty: str = Field(
        default="",
        validation_alias=AliasChoices("difficulty", "difficulty_level"),
        description="Difficulty level for this question.",
    )
    reason_for_asking: str = Field(default="", description="Why this question is job-relevant.")
    resume_grounding: str = Field(default="", description="Resume evidence connected to the question.")
    job_alignment: str = Field(default="", description="Job requirement connected to the question.")
    expected_strong_answer_signals: list[str] = Field(
        default_factory=list,
        description="Evidence expected in a strong answer.",
    )
    red_flags: list[str] = Field(default_factory=list, description="Weak or risky answer signals.")
    follow_up_questions: list[str] | None = Field(
        default=None,
        description=(
            "Omit in the initial interview plan; dynamic follow-up is generated "
            "after the candidate answer is evaluated."
        ),
    )
    scoring_guidance: QuestionScoringGuidance | None = None


class QuestionCoverageSummary(BaseModel):
    competencies_covered: list[str]
    techniques_used: list[str]
    notes: str


class QuestionLegacyCompatibility(BaseModel):
    question: str
    type: str
    difficulty: str
    focus_area: str
    why_this_question: str
    expected_good_answer_points: list[str]


class DocumentBriefOutput(BaseModel):
    candidate_summary: str = Field(
        default="",
        description="Compact summary of the candidate profile and relevant background.",
    )
    role_summary: str = Field(
        default="",
        description="Compact summary of the target role and hiring context.",
    )
    key_resume_evidence: list[str] = Field(
        default_factory=list,
        description="Most relevant resume evidence to use during evaluation.",
    )
    key_job_requirements: list[str] = Field(
        default_factory=list,
        description="Most important job requirements to use during evaluation.",
    )
    role_alignment_notes: list[str] = Field(
        default_factory=list,
        description="Concise notes linking resume evidence to job needs.",
    )
    fairness_notes: list[str] = Field(
        default_factory=list,
        description="Relevant fairness or evidence-boundary notes.",
    )


class GeneratedQuestionOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    interview_stage: str = ""
    seniority_level: str | None = None
    difficulty_level: str | None = None
    question_count: int = 0
    document_brief: DocumentBriefOutput | None = None
    questions: list[InterviewQuestionOutput] = Field(default_factory=list)
    coverage_summary: QuestionCoverageSummary | None = None
    legacy_compatibility: QuestionLegacyCompatibility | None = None

    @model_validator(mode="before")
    @classmethod
    def _wrap_list(cls, v: Any) -> Any:
        if isinstance(v, list):
            return {"questions": v, "question_count": len(v)}
        return v


class EvaluationCriterionScore(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    criterion: str = Field(
        default="",
        validation_alias=AliasChoices("criterion", "name"),
    )
    weight: float = 0
    score: float = 0
    weighted_score: float = 0
    reason: str = Field(
        default="",
        validation_alias=AliasChoices("reason", "justification", "evidence"),
    )
    evidence_from_answer: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    improvement_advice: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_score_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        if not normalized.get("criterion") and normalized.get("name"):
            normalized["criterion"] = normalized["name"]

        evidence = normalized.get("evidence")
        justification = normalized.get("justification")
        if not normalized.get("reason"):
            normalized["reason"] = justification or evidence or ""

        if not normalized.get("evidence_from_answer") and evidence:
            normalized["evidence_from_answer"] = (
                evidence if isinstance(evidence, list) else [str(evidence)]
            )

        if (
            not normalized.get("weighted_score")
            and isinstance(normalized.get("weight"), (int, float))
            and isinstance(normalized.get("score"), (int, float))
        ):
            normalized["weighted_score"] = (
                float(normalized["weight"]) * float(normalized["score"]) / 100.0
            )

        return normalized


class DeliveryAssessment(BaseModel):
    """How the answer was delivered, grounded in speech/voice (and face) metrics."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    fluency_rating: str = Field(
        default="",
        description="Overall delivery fluency, e.g. weak / fair / strong.",
    )
    voice_steadiness: str = Field(
        default="",
        description="Vocal steadiness, e.g. steady / mildly_unstable / shaky.",
    )
    observations: list[str] = Field(
        default_factory=list,
        description="Specific delivery observations grounded in the metrics.",
    )
    impact_on_communication: str = Field(
        default="",
        description="How delivery affected the Communication Clarity score.",
    )


class CandidateCoaching(BaseModel):
    better_answer_strategy: str
    example_improvement: str


class FairnessCheck(BaseModel):
    used_only_job_relevant_evidence: bool
    ignored_protected_characteristics: bool
    notes: str


class EvaluationLegacyCompatibility(BaseModel):
    overall_score: float
    category_scores: dict[str, Any]
    strengths: list[str]
    weaknesses: list[str]
    missing_details: list[str]
    improved_answer: str
    next_advice: str


class EvaluatedAnswerOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    overall_score: float = Field(
        default=0,
        validation_alias=AliasChoices("overall_score", "score", "final_score"),
    )
    overall_rating: str = ""
    hiring_signal: str = "mixed"
    confidence: str = "medium"
    summary: str = ""
    criteria_scores: list[EvaluationCriterionScore] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "criteria_scores",
            "criterion_scores",
            "scores",
            "rubric_scores",
        ),
    )
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    candidate_coaching: CandidateCoaching | None = None
    delivery_assessment: DeliveryAssessment | None = None
    fairness_check: FairnessCheck | None = None
    legacy_compatibility: EvaluationLegacyCompatibility | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_evaluation_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        if not normalized.get("summary"):
            normalized["summary"] = (
                normalized.get("feedback")
                or normalized.get("comments")
                or normalized.get("overall_feedback")
                or ""
            )

        if not normalized.get("criteria_scores"):
            for key in ("criterion_scores", "scores", "rubric_scores"):
                raw_scores = normalized.get(key)
                if isinstance(raw_scores, list):
                    normalized["criteria_scores"] = raw_scores
                    break
                if isinstance(raw_scores, dict):
                    normalized["criteria_scores"] = cls._scores_mapping_to_list(
                        raw_scores,
                        normalized.get("evidence"),
                    )
                    break

        return normalized

    @staticmethod
    def _scores_mapping_to_list(
        scores: dict[str, Any],
        evidence: Any,
    ) -> list[dict[str, Any]]:
        evidence_by_criterion = evidence if isinstance(evidence, dict) else {}
        criteria_scores = []

        for criterion, raw_score in scores.items():
            item: dict[str, Any] = {"criterion": str(criterion)}

            if isinstance(raw_score, dict):
                item.update(raw_score)
                item.setdefault("criterion", str(criterion))
            else:
                item["score"] = raw_score

            criterion_evidence = evidence_by_criterion.get(criterion)
            if criterion_evidence:
                item.setdefault("reason", str(criterion_evidence))
                item.setdefault("evidence_from_answer", [str(criterion_evidence)])

            criteria_scores.append(item)

        return criteria_scores


class TurnDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    action: Literal["follow_up", "next_question", "final_report"] = Field(
        description="Next graph action after evaluating the candidate answer."
    )
    reason: str = Field(
        default="",
        validation_alias=AliasChoices(
            "reason",
            "rationale",
            "justification",
            "explanation",
        ),
        description="Short evidence-grounded reason for the action.",
    )
    follow_up_question: str | None = Field(
        default=None,
        validation_alias=AliasChoices("follow_up_question", "next_question", "follow_up"),
        description="Follow-up question to ask when action is follow_up.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_question_fields(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return v
        # LLM sometimes returns next_question / follow_up_question as a full
        # question object instead of a plain string — extract just the text.
        v = dict(v)
        if not v.get("reason"):
            notes = v.get("notes")
            if isinstance(notes, list):
                v["reason"] = " ".join(str(note) for note in notes if note)
            elif isinstance(notes, str):
                v["reason"] = notes

        for key in ("next_question", "follow_up_question", "follow_up"):
            val = v.get(key)
            if isinstance(val, dict):
                v[key] = val.get("question") or val.get("question_text") or ""
            elif isinstance(val, list):
                first = val[0] if val else ""
                if isinstance(first, dict):
                    v[key] = first.get("question") or first.get("question_text") or ""
                else:
                    v[key] = str(first) if first else ""
        return v
    next_question_id: str | None = Field(
        default=None,
        description="Planned question id to ask next when action is next_question.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Routing notes for traceability, not hidden reasoning.",
    )


class FinalInterviewReportOutput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    overall_recommendation: str = Field(
        default="",
        validation_alias=AliasChoices(
            "overall_recommendation",
            "recommendation",
            "hiring_recommendation",
            "decision",
        ),
        description="Overall interview recommendation or hiring signal.",
    )
    summary: str = Field(
        default="",
        validation_alias=AliasChoices(
            "summary",
            "overall_summary",
            "final_summary",
        ),
        description="Concise final interview summary.",
    )
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_highlights: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence_highlights", "evidence"),
    )
    question_summaries: list[dict[str, Any]] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "suggested_next_steps",
            "next_steps",
            "recommendations",
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_report_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        recommendation = normalized.get("recommendation")
        if not normalized.get("overall_recommendation") and recommendation:
            normalized["overall_recommendation"] = str(recommendation)

        if not normalized.get("summary"):
            if recommendation:
                normalized["summary"] = str(recommendation)
            else:
                strengths = normalized.get("strengths") or []
                risks = normalized.get("risks") or []
                summary_parts = []
                if strengths:
                    summary_parts.append(f"Strengths: {', '.join(map(str, strengths[:2]))}")
                if risks:
                    summary_parts.append(f"Risks: {', '.join(map(str, risks[:2]))}")
                normalized["summary"] = "; ".join(summary_parts)

        if not normalized.get("suggested_next_steps") and normalized.get("next_steps"):
            normalized["suggested_next_steps"] = normalized["next_steps"]

        evidence = normalized.get("evidence")
        if isinstance(evidence, list):
            if not normalized.get("question_summaries"):
                normalized["question_summaries"] = [
                    item for item in evidence if isinstance(item, dict)
                ]
            if not normalized.get("evidence_highlights"):
                normalized["evidence_highlights"] = [
                    cls._format_evidence_highlight(item)
                    for item in evidence
                    if item
                ]

        return normalized

    @staticmethod
    def _format_evidence_highlight(item: Any) -> str:
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return str(item)

        question = item.get("question") or "Question"
        score = item.get("overall_score")
        strengths = item.get("strengths_cited") or []
        weaknesses = item.get("weaknesses_cited") or []
        parts = [str(question)]
        if score is not None:
            parts.append(f"score {score}")
        if strengths:
            parts.append(f"strengths: {', '.join(map(str, strengths[:2]))}")
        if weaknesses:
            parts.append(f"gaps: {', '.join(map(str, weaknesses[:2]))}")

        return " | ".join(parts)
