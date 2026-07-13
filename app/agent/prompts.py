"""Compact dynamic prompt builders for the interview agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate

from app.agent.profile import (
    AgentProfile,
    default_rubric,
    get_agent_profile,
)


PromptSection = tuple[str, str, str, bool]

_PROMPT_SECTIONS: list[PromptSection] = [
    ("system", "You are {role}", "role", True),
    ("system", "{system_instruction}", "system_instruction", True),
    ("system", "Resume JSON:\n{resume_json}", "resume_json", False),
    ("system", "Job description JSON:\n{job_description_json}", "job_description_json", False),
    ("system", "Document brief JSON:\n{document_brief_json}", "document_brief_json", False),
    ("system", "Interview config JSON:\n{interview_config_json}", "interview_config_json", False),
    ("system", "Evaluation config JSON:\n{evaluation_config_json}", "evaluation_config_json", False),
    ("system", "Rubric JSON:\n{rubric_json}", "rubric_json", False),
    ("system", "Rating anchors JSON:\n{rating_anchors_json}", "rating_anchors_json", False),
    ("system", "Question JSON:\n{question_json}", "question_json", False),
    ("system", "Expected answer signals:\n{expected_answer_signals}", "expected_answer_signals", False),
    ("system", "Candidate answer:\n{candidate_answer}", "candidate_answer", False),
    ("system", "Delivery metrics JSON:\n{delivery_metrics_json}", "delivery_metrics_json", False),
    ("system", "Interview limits JSON:\n{interview_limits_json}", "interview_limits_json", False),
    ("system", "Current question JSON:\n{current_question_json}", "current_question_json", False),
    ("system", "Latest evaluation JSON:\n{latest_evaluation_json}", "latest_evaluation_json", False),
    ("system", "Prior turns JSON:\n{turns_json}", "turns_json", False),
    ("system", "Interview plan JSON:\n{interview_plan_json}", "interview_plan_json", False),
    ("human", "Task:\n{task}", "task", True),
]

_EMPTY_TEXT_MARKERS = {"", "{}", "[]", "null", '""', "no context provided."}

TECHNIQUE_GUIDANCE = {
    "project_deep_dive": "Deeply examine a real project or experience from the resume.",
    "technical_probe": "Probe a specific implementation detail, tool, concept, or technical tradeoff.",
    "situational": "Use a realistic job-related scenario to test applied judgment.",
    "behavioral_star": "Ask for past behavior using the Situation, Task, Action, Result structure.",
}

NON_EMPTY_OUTPUT_RULE = (
    "Do not leave output fields blank. Every included string must contain a "
    "specific, useful value; every included list must contain at least one "
    "meaningful item. If a field cannot be supported by the provided evidence "
    "and the schema allows omission, omit that field instead of returning an "
    "empty string, null, [], or {}."
)

QUESTION_SYSTEM_INSTRUCTION = (
    "Generate fair, job-relevant structured interview questions from the provided "
    "resume and job description. Return only the bound GeneratedQuestionOutput. "
    f"{NON_EMPTY_OUTPUT_RULE} "
    "If seniority_level or difficulty_level is null or not provided, infer the "
    "most appropriate value from the job description, resume evidence, and "
    "interview stage before generating questions. "
    "Do not pre-generate follow-up questions in the interview plan; omit "
    "\"follow_up_questions\" because follow-ups must be generated only after "
    "reviewing the candidate answer and evaluation. "
    "Prefer balanced coverage across the configured question techniques; when "
    "question_count is sufficient, try to use each configured technique at least "
    "once, but do not force a technique that is not supported by the resume or "
    "job description evidence. In coverage_summary, state which techniques were "
    "used and briefly explain any configured technique that was skipped. "
    "Also create a compact document_brief that preserves the most important "
    "candidate evidence, role requirements, alignment notes, and fairness "
    "boundaries needed for later evaluation and follow-up decisions. "
    "Include \"expected_strong_answer_signals\", \"red_flags\", "
    "\"reason_for_asking\", \"resume_grounding\", and \"job_alignment\"."
)

EVALUATION_SYSTEM_INSTRUCTION = (
    "Evaluate one candidate answer using only the provided question context, "
    "expected answer signals, candidate answer, rubric, and any included "
    "resume/job grounding. Return only the bound "
    f"EvaluatedAnswerOutput. {NON_EMPTY_OUTPUT_RULE} "
    "Return rubric scores only as criteria_scores, a list of objects with "
    "criterion, score, and reason; do not return scores as a JSON object/map. "
    "Score only observed answer evidence; do not infer "
    "missing skills. "
    "When delivery metrics JSON is provided (speaking rate, pauses/hesitation, "
    "filler words, repetitions, mean length of run, and voice steadiness such "
    "as jitter, shimmer, pitch variability, plus video presentation metrics "
    "such as face visibility, centered framing, brightness, blur, head movement, "
    "multiple faces, and optional happy/emotion availability), factor them into "
    "the Communication Clarity criterion and populate delivery_assessment. "
    "Treat delivery metrics as supporting signals about how the answer was "
    "delivered, not as the sole basis for the score, and never penalize accent, "
    "non-native pronunciation, or protected characteristics."
)

TURN_DECISION_SYSTEM_INSTRUCTION = (
    "Choose the next interview action. Return only the bound TurnDecisionOutput "
    f"with action follow_up, next_question, or final_report. {NON_EMPTY_OUTPUT_RULE} "
    "Always include a non-empty reason explaining the selected action. Generate a "
    "follow_up_question only after reviewing the current candidate answer and "
    "latest evaluation. When action is follow_up, return exactly one concise "
    "follow_up_question. The follow-up must be one integrated question that covers "
    "the most important missing evidence from the latest evaluation; do not split "
    "it into multiple independent questions, a numbered list, or multiple question "
    "marks. You may use one main question with an \"include X, Y, and Z\" phrase "
    "to cover the key gaps. Never return multiple follow-up questions."
)

FINAL_REPORT_SYSTEM_INSTRUCTION = (
    "Create a concise final interview report from the observed interview plan "
    f"and turns. Return only the bound FinalInterviewReportOutput. {NON_EMPTY_OUTPUT_RULE}"
)


def _has_prompt_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return value.strip().lower() not in _EMPTY_TEXT_MARKERS

    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)

    return True


def build_prompt_template(payload: dict[str, Any]) -> ChatPromptTemplate:
    """Build a ChatPromptTemplate from only the prompt sections with data."""
    messages = []

    for role, template, key, required in _PROMPT_SECTIONS:
        if required or _has_prompt_value(payload.get(key)):
            messages.append((role, template))

    return ChatPromptTemplate.from_messages(messages)


def format_json(value: Any) -> str:
    """Render values as stable pretty JSON for LLM input."""
    if value is None:
        return ""

    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)

    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def format_list(items: list[str]) -> str:
    """Render a list as prompt bullets, or an empty marker when missing."""
    if not items:
        return ""

    return "\n".join(f"- {item}" for item in items)


def format_context(value: Any) -> str:
    """Render structured JSON or legacy list context."""
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        return format_list([str(item) for item in value if item])

    return format_json(value)


def normalize_weights(
    items: list[dict[str, Any]],
    weight_key: str = "weight",
) -> list[dict[str, Any]]:
    if not items:
        return []

    copied_items = [dict(item) for item in items]
    parsed_weights: list[float | None] = []

    for item in copied_items:
        raw_weight = item.get(weight_key)
        if isinstance(raw_weight, (int, float)):
            parsed_weights.append(max(float(raw_weight), 0.0))
        else:
            parsed_weights.append(None)

    if all(weight is None for weight in parsed_weights):
        equal_weight = round(100.0 / len(copied_items), 2)
        for item in copied_items:
            item[weight_key] = equal_weight
        return copied_items

    numeric_weights = [weight or 0.0 for weight in parsed_weights]
    total_weight = sum(numeric_weights)

    if total_weight <= 0:
        equal_weight = round(100.0 / len(copied_items), 2)
        for item in copied_items:
            item[weight_key] = equal_weight
        return copied_items

    for index, item in enumerate(copied_items):
        item[weight_key] = round((numeric_weights[index] / total_weight) * 100.0, 2)

    return copied_items


def _profile_value(profile: AgentProfile, key: str, default: Any = None) -> Any:
    return profile.get(key, default)


def _rubric_payload(profile: AgentProfile) -> list[dict[str, Any]]:
    return normalize_weights(_profile_value(profile, "rubric") or default_rubric())


def _rating_anchors_payload(profile: AgentProfile) -> dict[str, str]:
    default_profile = get_agent_profile()
    return _profile_value(profile, "rating_anchors") or default_profile["rating_anchors"]


def _question_config_payload(
    *,
    interview_type: str,
    difficulty: str | None,
    profile: AgentProfile,
) -> dict[str, Any]:
    return {
        "interview_stage": _profile_value(profile, "interview_stage"),
        "seniority_level": _profile_value(profile, "seniority_level"),
        "difficulty_level": _profile_value(profile, "difficulty_level") or difficulty,
        "legacy_interview_type": interview_type,
        "legacy_difficulty": difficulty,
        "question_count": _profile_value(profile, "question_count"),
        "followup_policy": {
            "generate_followups_after_answer": True,
            "do_not_pregenerate_followups_in_plan": True,
            "max_followups_per_question": _profile_value(
                profile,
                "max_followups_per_question",
                1,
            ),
        },
        "technique_guidance": TECHNIQUE_GUIDANCE,
        "technique_coverage_policy": "prefer_balanced_coverage",
        "missing_value_policy": (
            "If seniority_level or difficulty_level is null, infer it from the "
            "job description and resume instead of assuming a default."
        ),
        "question_techniques": _profile_value(profile, "question_techniques", []),
        "competencies": normalize_weights(_profile_value(profile, "competencies", [])),
        "question_constraints": _profile_value(profile, "question_constraints", {}),
        "fairness_rules": _profile_value(profile, "fairness_rules", {}),
    }


def _evaluation_config_payload(profile: AgentProfile) -> dict[str, Any]:
    return {
        "evaluation_mode": _profile_value(profile, "evaluation_mode"),
        "scale": _profile_value(profile, "scale"),
        "evidence_required": _profile_value(profile, "evidence_required"),
        "fairness_rules": _profile_value(profile, "fairness_rules", {}),
    }


def _invoke_dynamic_prompt(payload: dict[str, Any]) -> ChatPromptValue:
    return build_prompt_template(payload).invoke(payload)


def build_question_chat_prompt(
    cv_context: Any,
    job_description_context: Any,
    interview_type: str,
    difficulty: str | None,
    profile: AgentProfile,
) -> ChatPromptValue:
    payload = {
        "role": _profile_value(profile, "role"),
        "system_instruction": (
            f"{_profile_value(profile, 'system_instruction')}\n"
            f"{QUESTION_SYSTEM_INSTRUCTION}"
        ),
        "resume_json": format_context(cv_context),
        "job_description_json": format_context(job_description_context),
        "interview_config_json": format_json(
            _question_config_payload(
                interview_type=interview_type,
                difficulty=difficulty,
                profile=profile,
            )
        ),
        "task": (
            "Generate the configured interview questions. Use the resume and job "
            "description as grounding evidence."
        ),
    }
    return _invoke_dynamic_prompt(payload)


def build_evaluation_chat_prompt(
    cv_context: Any,
    job_description_context: Any,
    question: str | dict[str, Any],
    expected_good_answer_points: list[str],
    student_answer: str,
    profile: AgentProfile,
    document_brief: Any = None,
    delivery_metrics: dict[str, Any] | None = None,
) -> ChatPromptValue:
    question_payload = (
        question if isinstance(question, dict) else {"question": question}
    )
    payload = {
        "role": _profile_value(profile, "role"),
        "system_instruction": (
            f"{_profile_value(profile, 'system_instruction')}\n"
            f"{EVALUATION_SYSTEM_INSTRUCTION}"
        ),
        "resume_json": format_context(cv_context),
        "job_description_json": format_context(job_description_context),
        "document_brief_json": format_context(document_brief),
        "evaluation_config_json": format_json(_evaluation_config_payload(profile)),
        "rubric_json": format_json(_rubric_payload(profile)),
        "rating_anchors_json": format_json(_rating_anchors_payload(profile)),
        "question_json": format_json(question_payload),
        "expected_answer_signals": format_list(expected_good_answer_points),
        "candidate_answer": student_answer,
        "delivery_metrics_json": format_json(delivery_metrics) if delivery_metrics else "",
        "task": "Evaluate the candidate answer against the rubric.",
    }
    return _invoke_dynamic_prompt(payload)


def build_turn_decision_chat_prompt(
    *,
    profile: AgentProfile,
    document_brief: Any = None,
    current_question: dict[str, Any],
    current_answer: str,
    latest_evaluation: dict[str, Any],
    turns: list[dict[str, Any]],
    current_question_index: int,
    planned_question_count: int,
    max_questions: int,
    current_followup_count: int,
    max_followups_per_question: int,
) -> ChatPromptValue:
    payload = {
        "role": _profile_value(profile, "role"),
        "system_instruction": (
            f"{_profile_value(profile, 'system_instruction')}\n"
            f"{TURN_DECISION_SYSTEM_INSTRUCTION}"
        ),
        "document_brief_json": format_context(document_brief),
        "interview_limits_json": format_json(
            {
                "current_question_index": current_question_index,
                "planned_question_count": planned_question_count,
                "max_questions": max_questions,
                "current_followup_count": current_followup_count,
                "max_followups_per_question": max_followups_per_question,
                "followup_generation_rule": (
                    "Follow-up questions are generated only at this decision "
                    "step after reviewing the candidate answer and evaluation. "
                    "If action is follow_up, return exactly one integrated "
                    "follow_up_question that covers the most important missing "
                    "evidence. Do not return multiple independent questions, "
                    "a numbered list, or multiple question marks."
                ),
            }
        ),
        "current_question_json": format_json(current_question),
        "candidate_answer": current_answer,
        "latest_evaluation_json": format_json(latest_evaluation),
        "turns_json": format_json(turns),
        "task": (
            "Select follow_up only when more evidence is needed and follow-up "
            "budget remains. If selecting follow_up, generate exactly one "
            "answer-aware, integrated follow_up_question now; otherwise select "
            "next_question or final_report."
        ),
    }
    return _invoke_dynamic_prompt(payload)


def build_final_report_chat_prompt(
    *,
    profile: AgentProfile,
    interview_plan: dict[str, Any],
    turns: list[dict[str, Any]],
    document_brief: Any = None,
) -> ChatPromptValue:
    payload = {
        "role": _profile_value(profile, "role"),
        "system_instruction": (
            f"{_profile_value(profile, 'system_instruction')}\n"
            f"{FINAL_REPORT_SYSTEM_INSTRUCTION}"
        ),
        "document_brief_json": format_context(document_brief),
        "interview_plan_json": format_json(interview_plan),
        "turns_json": format_json(turns),
        "task": "Summarize the completed interview with strengths, risks, evidence, and next steps.",
    }
    return _invoke_dynamic_prompt(payload)


def build_question_prompt(
    cv_context: Any,
    job_description_context: Any,
    interview_type: str,
    difficulty: str | None,
    profile: AgentProfile,
) -> str:
    return build_question_chat_prompt(
        cv_context=cv_context,
        job_description_context=job_description_context,
        interview_type=interview_type,
        difficulty=difficulty,
        profile=profile,
    ).to_string()


def build_evaluation_prompt(
    cv_context: Any,
    job_description_context: Any,
    question: str | dict[str, Any],
    expected_good_answer_points: list[str],
    student_answer: str,
    profile: AgentProfile,
    document_brief: Any = None,
    delivery_metrics: dict[str, Any] | None = None,
) -> str:
    return build_evaluation_chat_prompt(
        cv_context=cv_context,
        job_description_context=job_description_context,
        question=question,
        expected_good_answer_points=expected_good_answer_points,
        student_answer=student_answer,
        profile=profile,
        document_brief=document_brief,
        delivery_metrics=delivery_metrics,
    ).to_string()


QUESTION_PROMPT_TEMPLATE = build_prompt_template(
    {
        "role": "role",
        "system_instruction": QUESTION_SYSTEM_INSTRUCTION,
        "resume_json": "content",
        "job_description_json": "content",
        "interview_config_json": "content",
        "task": "task",
    }
)
EVALUATION_PROMPT_TEMPLATE = build_prompt_template(
    {
        "role": "role",
        "system_instruction": EVALUATION_SYSTEM_INSTRUCTION,
        "resume_json": "content",
        "job_description_json": "content",
        "document_brief_json": "content",
        "evaluation_config_json": "content",
        "rubric_json": "content",
        "rating_anchors_json": "content",
        "question_json": "content",
        "candidate_answer": "answer",
        "delivery_metrics_json": "content",
        "task": "task",
    }
)
TURN_DECISION_PROMPT_TEMPLATE = build_prompt_template(
    {
        "role": "role",
        "system_instruction": TURN_DECISION_SYSTEM_INSTRUCTION,
        "document_brief_json": "content",
        "interview_limits_json": "content",
        "current_question_json": "content",
        "latest_evaluation_json": "content",
        "turns_json": "content",
        "task": "task",
    }
)
FINAL_REPORT_PROMPT_TEMPLATE = build_prompt_template(
    {
        "role": "role",
        "system_instruction": FINAL_REPORT_SYSTEM_INSTRUCTION,
        "document_brief_json": "content",
        "interview_plan_json": "content",
        "turns_json": "content",
        "task": "task",
    }
)
PROMPT_TEMPLATE = build_prompt_template
