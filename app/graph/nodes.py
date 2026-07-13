"""LangGraph nodes for the interactive interview workflow."""

from __future__ import annotations

import json
from typing import Any

from langgraph.types import interrupt

from app.agent import llm_client
from app.agent.outputs import (
    EvaluatedAnswerOutput,
    FinalInterviewReportOutput,
    GeneratedQuestionOutput,
    TurnDecisionOutput,
    clean_empty_fields,
)
from app.agent.prompts import (
    build_evaluation_chat_prompt,
    build_final_report_chat_prompt,
    build_question_chat_prompt,
    build_turn_decision_chat_prompt,
    format_json,
    format_list,
)
from app.graph.state import CompactTurn, GraphState
from app.graph.schemas import QuestionRequest


def _trace(state: GraphState, node: str, message: str) -> list[dict[str, Any]]:
    if not state.get("debug_trace"):
        return []

    return [{"node": node, "message": message}]


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return clean_empty_fields(value.model_dump(exclude_none=True))
    if isinstance(value, dict):
        return clean_empty_fields(dict(value))
    return {}


def _question_text(question: dict[str, Any]) -> str:
    return str(question.get("question") or "")


def _question_expected_points(question: dict[str, Any]) -> list[str]:
    values = question.get("expected_strong_answer_signals") or question.get(
        "expected_good_answer_points"
    )
    if not isinstance(values, list):
        return []

    return [str(value) for value in values if value]


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    return [str(value) for value in values if value]


def _short_text(value: Any, max_chars: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text

    return text[: max_chars - 3].rstrip() + "..."


def _append_unique_text(
    values: list[str],
    value: Any,
    *,
    max_items: int,
    max_chars: int = 260,
) -> None:
    if len(values) >= max_items:
        return

    text = _short_text(value, max_chars=max_chars)
    if not text:
        return

    dedupe_key = text.lower()
    if dedupe_key in {item.lower() for item in values}:
        return

    values.append(text)


def _resume_item_brief(section_name: str, item: Any) -> str:
    if not isinstance(item, dict):
        return _short_text(item, max_chars=260)

    parts = []
    for key in (
        "job_title",
        "company",
        "project_name",
        "degree",
        "field_of_study",
        "institution",
        "summary",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))

    for key in ("bullets", "skills", "relevant_courses"):
        values = item.get(key)
        if isinstance(values, list) and values:
            parts.extend(str(value) for value in values[:2] if value)

    if not parts:
        parts = [
            f"{key}: {value}"
            for key, value in item.items()
            if value and not isinstance(value, (dict, list))
        ][:4]

    prefix = f"{section_name}: " if section_name else ""
    return _short_text(prefix + " | ".join(parts), max_chars=320)


def _document_brief_from_request(request: QuestionRequest) -> dict[str, Any]:
    resume = _model_dump(request.resume) if request.resume is not None else {}
    job_description = (
        _model_dump(request.job_description)
        if request.job_description is not None
        else {}
    )

    candidate = resume.get("candidate") if isinstance(resume, dict) else {}
    if not isinstance(candidate, dict):
        candidate = {}

    candidate_parts = [
        candidate.get("full_name"),
        candidate.get("headline"),
    ]
    candidate_summary = _short_text(
        " - ".join(str(part) for part in candidate_parts if part),
        max_chars=260,
    )

    key_resume_evidence: list[str] = []
    sections = resume.get("sections") if isinstance(resume, dict) else []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("section_name") or "")
            items = section.get("items") or []
            if not isinstance(items, list):
                continue
            for item in items:
                _append_unique_text(
                    key_resume_evidence,
                    _resume_item_brief(section_name, item),
                    max_items=8,
                    max_chars=320,
                )

    for item in request.cv_context:
        _append_unique_text(
            key_resume_evidence,
            item,
            max_items=8,
            max_chars=320,
        )

    role_parts = []
    if isinstance(job_description, dict):
        for key in (
            "role_title",
            "company",
            "seniority",
            "employment_type",
            "location",
            "summary",
        ):
            value = job_description.get(key)
            if value:
                role_parts.append(str(value))

    role_summary = _short_text(" | ".join(role_parts), max_chars=320)

    key_job_requirements: list[str] = []
    if isinstance(job_description, dict):
        for key in (
            "responsibilities",
            "requirements",
            "preferred_skills",
            "tech_stack",
        ):
            values = job_description.get(key) or []
            if isinstance(values, list):
                for value in values:
                    _append_unique_text(
                        key_job_requirements,
                        value,
                        max_items=10,
                        max_chars=240,
                    )

    for item in request.job_description_context:
        _append_unique_text(
            key_job_requirements,
            item,
            max_items=10,
            max_chars=320,
        )

    return clean_empty_fields(
        {
            "candidate_summary": candidate_summary,
            "role_summary": role_summary,
            "key_resume_evidence": key_resume_evidence,
            "key_job_requirements": key_job_requirements,
            "role_alignment_notes": [
                "Use the planned question's resume_grounding and job_alignment together with this brief.",
            ],
            "fairness_notes": [
                "Score only job-relevant observed evidence from the resume, job description, and candidate answers.",
                "Do not infer protected characteristics or missing skills that are not evidenced.",
            ],
        }
    )


def _pick_fields(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return clean_empty_fields(
        {
            key: source.get(key)
            for key in keys
            if key in source
        }
    )


def _ensure_question_ids(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, question in enumerate(questions, start=1):
        if not str(question.get("id") or "").strip():
            question["id"] = f"q{index}"

    return questions


def _compact_criteria_scores(scores: Any) -> list[dict[str, Any]]:
    if not isinstance(scores, list):
        return []

    compact_scores = []
    for score in scores:
        if not isinstance(score, dict):
            continue
        compact_scores.append(
            _pick_fields(
                score,
                (
                    "criterion",
                    "score",
                    "reason",
                    "missing_evidence",
                    "improvement_advice",
                ),
            )
        )

    return [
        score
        for score in compact_scores
        if score
    ]


def _compact_question_for_evaluation(question: dict[str, Any]) -> dict[str, Any]:
    return _pick_fields(
        question,
        (
            "id",
            "question",
            "competency",
            "technique",
            "difficulty",
            "reason_for_asking",
            "resume_grounding",
            "job_alignment",
            "is_follow_up",
            "parent_question_id",
        ),
    )


def _compact_question_for_candidate(question: dict[str, Any]) -> dict[str, Any]:
    return _pick_fields(
        question,
        (
            "id",
            "question",
            "competency",
            "difficulty",
            "is_follow_up",
            "parent_question_id",
        ),
    )


def _compact_question_for_decision(question: dict[str, Any]) -> dict[str, Any]:
    return _pick_fields(
        question,
        (
            "id",
            "question",
            "competency",
            "difficulty",
            "is_follow_up",
            "parent_question_id",
        ),
    )


def _compact_evaluation_for_decision(evaluation: dict[str, Any]) -> dict[str, Any]:
    compact = _pick_fields(
        evaluation,
        (
            "overall_score",
            "overall_rating",
            "hiring_signal",
            "confidence",
            "summary",
            "strengths",
            "weaknesses",
            "red_flags",
        ),
    )
    compact_scores = _compact_criteria_scores(evaluation.get("criteria_scores"))
    if compact_scores:
        compact["criteria_scores"] = compact_scores
    return clean_empty_fields(compact)


def _compact_turns_for_decision(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_turns = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        compact_turns.append(
            _pick_fields(
                turn,
                (
                    "question_index",
                    "question_id",
                    "question_text",
                    "is_follow_up",
                    "parent_question_id",
                    "overall_score",
                    "decision_action",
                ),
            )
        )

    return [
        turn
        for turn in compact_turns
        if turn
    ]


def _compact_interview_plan_for_report(plan: dict[str, Any]) -> dict[str, Any]:
    compact = _pick_fields(
        plan,
        (
            "interview_stage",
            "seniority_level",
            "difficulty_level",
            "question_count",
            "coverage_summary",
        ),
    )
    questions = []
    for question in plan.get("questions", []):
        if not isinstance(question, dict):
            continue
        questions.append(
            _pick_fields(
                question,
                (
                    "id",
                    "question",
                    "competency",
                    "technique",
                    "difficulty",
                    "reason_for_asking",
                    "resume_grounding",
                    "job_alignment",
                ),
            )
        )
    if questions:
        compact["questions"] = questions
    return clean_empty_fields(compact)


def _build_compact_turn(
    *,
    turn_index: int,
    question_index: int,
    question: dict[str, Any],
    answer: str,
    evaluation: dict[str, Any],
    decision: dict[str, Any],
    routed_action: str,
) -> CompactTurn:
    compact_turn: CompactTurn = {
        "turn_index": turn_index,
        "question_index": question_index + 1,
        "question_text": _question_text(question),
        "answer": answer,
        "decision_action": routed_action,
    }

    question_id = question.get("id")
    if question_id:
        compact_turn["question_id"] = str(question_id)

    if question.get("is_follow_up"):
        compact_turn["is_follow_up"] = True

    parent_question_id = question.get("parent_question_id")
    if parent_question_id:
        compact_turn["parent_question_id"] = str(parent_question_id)

    if evaluation.get("summary"):
        compact_turn["evaluation_summary"] = str(evaluation["summary"])

    if evaluation.get("overall_score") is not None:
        compact_turn["overall_score"] = float(evaluation["overall_score"])

    if evaluation.get("hiring_signal"):
        compact_turn["hiring_signal"] = evaluation["hiring_signal"]

    if evaluation.get("confidence"):
        compact_turn["confidence"] = evaluation["confidence"]

    for source_key, target_key in (
        ("strengths", "strengths"),
        ("weaknesses", "weaknesses"),
        ("red_flags", "red_flags"),
    ):
        values = _as_string_list(evaluation.get(source_key))
        if values:
            compact_turn[target_key] = values

    delivery_assessment = evaluation.get("delivery_assessment")
    if isinstance(delivery_assessment, dict) and delivery_assessment:
        compact_turn["delivery_assessment"] = delivery_assessment

    if decision.get("reason"):
        compact_turn["decision_reason"] = str(decision["reason"])

    if routed_action == "follow_up" and decision.get("follow_up_question"):
        compact_turn["follow_up_question"] = str(decision["follow_up_question"])

    return clean_empty_fields(compact_turn)


def _planned_question_limit(state: GraphState) -> int:
    planned_count = len(state.get("planned_questions", []))
    max_questions = int(state.get("max_questions") or planned_count or 0)
    if planned_count <= 0:
        return 0
    return min(max_questions, planned_count)


def _resume_context_from_request(request: QuestionRequest) -> str:
    if request.resume is not None:
        return format_json(request.resume)

    return format_list(request.cv_context)


def _job_context_from_request(request: QuestionRequest) -> str:
    if request.job_description is not None:
        return format_json(request.job_description)

    return format_list(request.job_description_context)


def start_interview_node(state: GraphState) -> GraphState:
    return {
        "status": "started",
        "last_node": "start_interview",
        "current_question_index": 0,
        "current_followup_count": 0,
        "turns": [],
        "turn_summaries": [],
        "evaluations": [],
        "errors": [],
        "trace": _trace(state, "start_interview", "Started interview graph."),
    }


def load_documents_node(state: GraphState) -> GraphState:
    from app.agent.profile import build_question_profile

    request_payload = state.get("request_payload") or {}
    request = QuestionRequest.model_validate(request_payload)
    profile = build_question_profile(request)
    max_followups_value = request_payload.get("max_followups_per_question")
    if max_followups_value is None:
        max_followups_value = state.get("max_followups_per_question")
    if max_followups_value is None:
        max_followups_value = profile.get("max_followups_per_question")
    requested_followups = int(
        max_followups_value if max_followups_value is not None else 1
    )
    profile_followup_limit = int(profile.get("max_followups_per_question") or 1)
    max_followups = min(
        max(0, requested_followups),
        max(0, profile_followup_limit),
    )

    return {
        "profile": profile,
        "resume_context": _resume_context_from_request(request),
        "job_description_context": _job_context_from_request(request),
        "document_brief": _document_brief_from_request(request),
        "interview_type": request.interview_type,
        "difficulty": request.difficulty,
        "max_questions": int(profile.get("question_count") or 0),
        "max_followups_per_question": max(0, max_followups),
        "status": "documents_loaded",
        "last_node": "load_documents",
        "trace": _trace(
            state,
            "load_documents",
            "Loaded structured resume and job description context.",
        ),
    }


def generate_plan_node(state: GraphState) -> GraphState:
    prompt = build_question_chat_prompt(
        cv_context=state["resume_context"],
        job_description_context=state["job_description_context"],
        interview_type=state["interview_type"],
        difficulty=state["difficulty"],
        profile=state["profile"],
    )
    result = llm_client.call_llm_with_structured_output(
        prompt,
        GeneratedQuestionOutput,
    )
    planned_questions = [
        clean_empty_fields(question.model_dump(exclude_none=True))
        for question in result.questions
    ]
    planned_questions = _ensure_question_ids(planned_questions)
    for question in planned_questions:
        question.pop("follow_up_questions", None)
    interview_plan = clean_empty_fields(result.model_dump(exclude_none=True))
    interview_questions = [
        question
        for question in interview_plan.get("questions", [])
        if isinstance(question, dict)
    ]
    _ensure_question_ids(interview_questions)
    for question in interview_questions:
        question.pop("follow_up_questions", None)
    document_brief = clean_empty_fields(
        interview_plan.get("document_brief") or state.get("document_brief", {})
    )

    return {
        "request_payload": {},
        "resume_context": "",
        "job_description_context": "",
        "document_brief": document_brief,
        "interview_plan": _compact_interview_plan_for_report(interview_plan),
        "planned_questions": planned_questions,
        "status": "plan_ready",
        "last_node": "generate_plan",
        "node_outputs": {"interview_plan_schema": "GeneratedQuestionOutput"},
        "trace": _trace(
            state,
            "generate_plan",
            f"Generated interview plan with {len(planned_questions)} questions.",
        ),
    }


def route_after_plan(state: GraphState) -> str:
    if _planned_question_limit(state) <= 0:
        return "final_report"
    return "ask_question"


def _select_question_from_plan(state: GraphState) -> tuple[int, dict[str, Any]]:
    """Select the next question from the plan, prioritizing pending follow-up."""
    planned_questions = state.get("planned_questions", [])
    question_index = int(state.get("current_question_index") or 0)

    if question_index < 0 or question_index >= len(planned_questions):
        raise ValueError("No planned question is available for the current index.")

    base_question = dict(planned_questions[question_index])
    pending_followup = str(state.get("pending_followup_question") or "").strip()
    if pending_followup:
        return question_index, {
            **base_question,
            "id": f"{base_question.get('id', f'q{question_index + 1}')}_followup",
            "question": pending_followup,
            "is_follow_up": True,
            "parent_question_id": base_question.get("id"),
        }

    return question_index, base_question


def ask_question_node(state: GraphState) -> GraphState:
    question_index, current_question = _select_question_from_plan(state)
    is_follow_up = bool(current_question.get("is_follow_up"))
    trace_node = "ask_followup_question" if is_follow_up else "ask_question"
    trace_message = (
        "Received candidate answer for follow-up question."
        if is_follow_up
        else "Received candidate answer."
    )

    answer_payload = interrupt(
        {
            "type": "candidate_answer_required",
            "question_index": question_index,
            "question": _compact_question_for_candidate(current_question),
        }
    )

    delivery_metrics: dict[str, Any] = {}
    answer_source = "text"

    if isinstance(answer_payload, dict):
        answer = str(answer_payload.get("answer", "")).strip()
        raw_delivery_metrics = answer_payload.get("delivery_metrics")
        if isinstance(raw_delivery_metrics, dict):
            delivery_metrics = clean_empty_fields(raw_delivery_metrics)
        answer_source = str(answer_payload.get("answer_source") or answer_source)
    else:
        answer = str(answer_payload or "").strip()

    if not answer:
        raise ValueError("Candidate answer is required to continue the interview.")

    return {
        "current_question": current_question,
        "current_answer": answer,
        "current_answer_source": answer_source,
        "current_delivery_metrics": delivery_metrics,
        "status": "answer_received",
        "last_node": "ask_question",
        "trace": _trace(state, trace_node, trace_message),
    }


def evaluate_answer_node(state: GraphState) -> GraphState:
    current_question = state["current_question"]

    prompt = build_evaluation_chat_prompt(
        cv_context="",
        job_description_context="",
        question=_compact_question_for_evaluation(current_question),
        expected_good_answer_points=_question_expected_points(current_question),
        student_answer=state["current_answer"],
        profile=state["profile"],
        document_brief=state.get("document_brief"),
        delivery_metrics=state.get("current_delivery_metrics") or None,
    )
    result = llm_client.call_llm_with_structured_output(
        prompt,
        EvaluatedAnswerOutput,
        temperature=0.0,
    )
    result_json = clean_empty_fields(result.model_dump(exclude_none=True))

    return {
        "latest_evaluation": result_json,
        "evaluations": [result_json],
        "status": "answer_evaluated",
        "last_node": "evaluate_answer",
        "node_outputs": {"latest_evaluation_schema": "EvaluatedAnswerOutput"},
        "trace": _trace(state, "evaluate_answer", "Evaluated candidate answer."),
    }


def _next_action_with_limits(
    state: GraphState,
    decision: TurnDecisionOutput,
) -> str:
    action = decision.action
    question_index = int(state.get("current_question_index") or 0)
    followup_count = int(state.get("current_followup_count") or 0)
    max_followups = int(state.get("max_followups_per_question") or 0)
    next_question_index = question_index + 1

    if action == "follow_up" and followup_count >= max_followups:
        action = "next_question"

    if action == "next_question" and next_question_index >= _planned_question_limit(state):
        action = "final_report"

    return action


def _decision_reason(
    *,
    state: GraphState,
    decision_json: dict[str, Any],
    evaluation: dict[str, Any],
    routed_action: str,
) -> str:
    explicit_reason = _short_text(decision_json.get("reason"))
    requested_action = str(decision_json.get("action") or routed_action)

    if explicit_reason and requested_action == routed_action:
        return explicit_reason

    if explicit_reason:
        return _short_text(
            f"{explicit_reason} Routed to {routed_action} because the workflow limits changed the action."
        )

    summary = _short_text(evaluation.get("summary"), max_chars=150)
    question_index = int(state.get("current_question_index") or 0)
    next_question_index = question_index + 1
    followup_count = int(state.get("current_followup_count") or 0)
    max_followups = int(state.get("max_followups_per_question") or 0)

    if requested_action == "follow_up" and routed_action != "follow_up":
        if not decision_json.get("follow_up_question"):
            return (
                "The model selected follow-up but did not provide a follow-up "
                "question, so the workflow moved on."
            )
        if followup_count >= max_followups:
            return (
                "The follow-up limit for this planned question was reached, "
                f"so the workflow routed to {routed_action}."
            )

    if requested_action == "next_question" and routed_action == "final_report":
        if next_question_index >= _planned_question_limit(state):
            return "No planned questions remain, so the workflow created the final report."

    if routed_action == "follow_up":
        if summary:
            return f"More evidence is needed before moving on; latest evaluation: {summary}"
        return "More evidence is needed before moving on, so the workflow asked a follow-up."

    if routed_action == "next_question":
        if summary:
            return f"The current answer was evaluated; moving to the next planned question. Latest evaluation: {summary}"
        return "The current answer was evaluated, so the workflow moved to the next planned question."

    if summary:
        return f"The interview is ready for final reporting after the latest evaluation: {summary}"

    return "The interview is ready for final reporting from the collected turns."


def decide_next_node(state: GraphState) -> GraphState:
    current_question = state["current_question"]
    latest_evaluation = _model_dump(state["latest_evaluation"])
    turns = _compact_turns_for_decision(list(state.get("turn_summaries", [])))

    prompt = build_turn_decision_chat_prompt(
        profile=state["profile"],
        document_brief=state.get("document_brief"),
        current_question=_compact_question_for_decision(current_question),
        current_answer=state["current_answer"],
        latest_evaluation=_compact_evaluation_for_decision(latest_evaluation),
        turns=turns,
        current_question_index=int(state.get("current_question_index") or 0),
        planned_question_count=len(state.get("planned_questions", [])),
        max_questions=int(state.get("max_questions") or 0),
        current_followup_count=int(state.get("current_followup_count") or 0),
        max_followups_per_question=int(
            state.get("max_followups_per_question") or 0
        ),
    )
    decision = llm_client.call_llm_with_structured_output(
        prompt,
        TurnDecisionOutput,
    )
    action = _next_action_with_limits(state, decision)
    question_index = int(state.get("current_question_index") or 0)
    followup_count = int(state.get("current_followup_count") or 0)
    followup_question = (decision.follow_up_question or "").strip()

    if action == "follow_up" and not followup_question:
        next_question_index = question_index + 1
        action = (
            "final_report"
            if next_question_index >= _planned_question_limit(state)
            else "next_question"
        )

    decision_json = clean_empty_fields(decision.model_dump(exclude_none=True))
    decision_json["reason"] = _decision_reason(
        state=state,
        decision_json=decision_json,
        evaluation=latest_evaluation,
        routed_action=action,
    )
    compact_turn = _build_compact_turn(
        turn_index=len(state.get("turn_summaries", [])) + 1,
        question_index=question_index,
        question=current_question,
        answer=state["current_answer"],
        evaluation=latest_evaluation,
        decision=decision_json,
        routed_action=action,
    )
    turn = {
        "question_index": question_index,
        "question": current_question,
        "answer": state["current_answer"],
        "evaluation": latest_evaluation,
        "decision": decision_json,
        "routed_action": action,
    }
    answer_source = state.get("current_answer_source")
    if answer_source:
        turn["answer_source"] = answer_source
    delivery_metrics = state.get("current_delivery_metrics")
    if delivery_metrics:
        turn["delivery_metrics"] = delivery_metrics

    updates: GraphState = {
        "latest_decision": decision_json,
        "turns": [turn],
        "turn_summaries": [compact_turn],
        "status": "turn_decided",
        "last_node": "decide_next",
        "next_node": action,
        "node_outputs": {"latest_decision_schema": "TurnDecisionOutput"},
        "trace": _trace(state, "decide_next", f"Decided next action: {action}."),
    }

    if action == "follow_up":
        updates["pending_followup_question"] = followup_question
        updates["current_followup_count"] = followup_count + 1
    elif action == "next_question":
        updates["current_question_index"] = question_index + 1
        updates["current_followup_count"] = 0
        updates["pending_followup_question"] = None
    else:
        updates["pending_followup_question"] = None

    return updates


def route_after_decision(state: GraphState) -> str:
    if state.get("next_node") == "follow_up":
        return "ask_question"
    if state.get("next_node") == "next_question":
        return "ask_question"
    return "final_report"


def final_report_node(state: GraphState) -> GraphState:
    interview_plan = _compact_interview_plan_for_report(
        _model_dump(state.get("interview_plan"))
    )
    turns = list(state.get("turn_summaries") or state.get("turns", []))
    prompt = build_final_report_chat_prompt(
        profile=state["profile"],
        interview_plan=interview_plan,
        turns=turns,
        document_brief=state.get("document_brief"),
    )
    result = llm_client.call_llm_with_structured_output(
        prompt,
        FinalInterviewReportOutput,
    )
    result_json = clean_empty_fields(result.model_dump(exclude_none=True))

    return {
        "final_report": result_json,
        "final_answer": json.dumps(result_json, ensure_ascii=False),
        "status": "completed",
        "last_node": "final_report",
        "node_outputs": {"final_report_schema": "FinalInterviewReportOutput"},
        "trace": _trace(state, "final_report", "Created final interview report."),
    }
