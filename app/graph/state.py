"""Typed state contract shared by all LangGraph interview workflow nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


WorkflowStatus = Literal[
    "pending",
    "started",
    "documents_loaded",
    "plan_ready",
    "answer_received",
    "answer_evaluated",
    "turn_decided",
    "completed",
    "failed",
]

TurnAction = Literal["follow_up", "next_question", "final_report"]
HiringSignal = Literal["strong", "mixed", "weak"]
Confidence = Literal["low", "medium", "high"]


def merge_dicts(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(left or {})
    out.update(right or {})
    return out


class CriterionScoreState(TypedDict, total=False):
    criterion: str
    weight: float
    score: float
    weighted_score: float
    reason: str
    evidence_from_answer: list[str]
    missing_evidence: list[str]
    improvement_advice: str


class EvaluationState(TypedDict, total=False):
    overall_score: float
    overall_rating: str
    hiring_signal: HiringSignal
    confidence: Confidence
    summary: str
    criteria_scores: list[CriterionScoreState]
    strengths: list[str]
    weaknesses: list[str]
    red_flags: list[str]
    follow_up_questions: list[str]
    candidate_coaching: dict[str, Any]
    fairness_check: dict[str, Any]


class DecisionState(TypedDict, total=False):
    action: TurnAction
    reason: str
    follow_up_question: str
    next_question_id: str
    notes: list[str]


class CompactTurn(TypedDict, total=False):
    turn_index: int
    question_index: int
    question_id: str
    question_text: str
    is_follow_up: bool
    parent_question_id: str
    answer: str
    evaluation_summary: str
    overall_score: float
    hiring_signal: HiringSignal
    confidence: Confidence
    strengths: list[str]
    weaknesses: list[str]
    red_flags: list[str]
    delivery_assessment: dict[str, Any]
    decision_action: TurnAction
    decision_reason: str
    follow_up_question: str


class FinalReportState(TypedDict, total=False):
    candidate_name: str
    overall_recommendation: str
    summary: str
    strengths: list[str]
    risks: list[str]
    evidence_highlights: list[str]
    question_summaries: list[dict[str, Any]]
    suggested_next_steps: list[str]


class GraphState(TypedDict, total=False):
    # input
    request_payload: dict[str, Any]
    debug_trace: bool

    # loaded documents / config
    profile: dict[str, Any]
    resume_context: str
    job_description_context: str
    document_brief: dict[str, Any]
    interview_type: str
    difficulty: str | None
    max_questions: int
    max_followups_per_question: int

    # interview plan
    interview_plan: dict[str, Any]
    planned_questions: list[dict[str, Any]]
    current_question_index: int
    current_followup_count: int
    pending_followup_question: str | None

    # current turn
    status: WorkflowStatus
    last_node: str
    current_question: dict[str, Any]
    current_answer: str
    current_answer_source: str
    current_delivery_metrics: dict[str, Any]
    latest_evaluation: EvaluationState
    latest_decision: DecisionState
    final_report: FinalReportState
    final_answer: str

    # routing control
    next_node: str

    # compact memory for final report
    turn_summaries: Annotated[list[CompactTurn], operator.add]

    # debug / trace only
    turns: Annotated[list[dict[str, Any]], operator.add]
    evaluations: Annotated[list[EvaluationState], operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    node_outputs: Annotated[dict[str, Any], merge_dicts]


InterviewWorkflowState = GraphState
