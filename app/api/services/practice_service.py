"""Practice-mode operations built on the existing InterviewAgent."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.agent import llm_client
from app.agent.agent import InterviewAgent
from app.agent.profile import build_evaluation_profile, get_agent_profile
from app.api import deps
from app.graph.schemas import EvaluationRequest


# --- Question generation ----------------------------------------------------


def generate_questions(
    profile_record: dict[str, Any],
    question_count: int | None = None,
) -> dict[str, Any]:
    """Generate interview questions grounded in the profile's resume + JD."""
    resume = deps.load_resume_or_404(profile_record["resume_version"])
    jd_text = profile_record.get("job_description") or ""

    agent_profile = get_agent_profile(question_count=question_count)
    agent = InterviewAgent(agent_profile)
    result = agent.generate_question_structured(
        cv_context=resume,
        job_description_context=jd_text,
        interview_type="technical",
        difficulty=None,
    )
    return result.model_dump(exclude_none=True)


# --- Answer evaluation ------------------------------------------------------


def evaluate_answer(
    profile_record: dict[str, Any],
    question: str,
    answer: str,
    expected_good_answer_points: list[str] | None = None,
    delivery_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one answer, mirroring the CLI ``evaluate-answer`` flow."""
    resume = deps.load_resume_or_404(profile_record["resume_version"])
    jd_text = profile_record.get("job_description") or ""

    request = EvaluationRequest.model_validate(
        {
            "resume": resume,
            "job_description_context": [jd_text],
            "question": question,
            "student_answer": answer,
            "expected_good_answer_points": list(expected_good_answer_points or []),
            "delivery_metrics": delivery_metrics or None,
        }
    )

    profile = build_evaluation_profile(request)
    cv_context = request.resume if request.resume is not None else request.cv_context
    job_context = (
        request.job_description
        if request.job_description is not None
        else request.job_description_context
    )

    result = InterviewAgent(profile).evaluate_answer_structured(
        cv_context=cv_context,
        job_description_context=job_context,
        question=request.question,
        expected_good_answer_points=request.expected_good_answer_points,
        student_answer=request.student_answer,
        delivery_metrics=request.delivery_metrics,
    )
    return result.model_dump(exclude_none=True)


# --- Final session report (candidate coaching) ------------------------------


class _PracticeReport(BaseModel):
    """Improvement-focused report addressed to the candidate."""

    overall_summary: str = Field(..., description="Encouraging, honest summary in 'you' voice.")
    readiness: str = Field(..., description="Short label, e.g. 'Almost there' / 'Needs practice'.")
    top_strengths: list[str] = Field(default_factory=list)
    areas_to_improve: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(
        default_factory=list, description="Concrete, actionable practice steps."
    )
    focus_next: str | None = Field(default=None, description="One line: what to focus on next.")


_REPORT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a supportive but honest interview coach. Write a report "
            "addressed directly to the candidate (use 'you') to help them improve "
            "before the real interview. Ground every point in the answered "
            "questions and their evaluations provided — do not invent evidence. "
            "Be specific and actionable.\n\n"
            "Respond with ONLY a single valid JSON object and nothing else: no "
            "markdown, no headings, no bold, no commentary before or after. Use "
            "exactly these keys:\n"
            '  "overall_summary": string,\n'
            '  "readiness": string (a short label, e.g. "Almost there"),\n'
            '  "top_strengths": array of strings,\n'
            '  "areas_to_improve": array of strings,\n'
            '  "action_items": array of strings (concrete things to practice),\n'
            '  "focus_next": string (one line).',
        ),
        (
            "human",
            "TARGET ROLE: {job} at {company}\n\n"
            "ANSWERED QUESTIONS (each with the candidate's answer and its "
            "evaluation):\n{turns_json}\n\n"
            "Return the JSON object now.",
        ),
    ]
)


def generate_report(
    profile_record: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize a practice session into coaching feedback for the candidate."""
    prompt = _REPORT_PROMPT.invoke(
        {
            "job": profile_record.get("job_title") or "the role",
            "company": profile_record.get("company") or "the company",
            "turns_json": json.dumps(turns, ensure_ascii=False, indent=2),
        }
    )
    result = llm_client.call_llm_with_structured_output(prompt, _PracticeReport)
    return result.model_dump(exclude_none=True)


# --- Per-question coaching (strengths + what to improve, for each answer) ----


class _TurnCoachingItem(BaseModel):
    index: int = Field(..., description="0-based index of the answered question.")
    strengths: list[str] = Field(
        default_factory=list,
        description="1-2 concise, specific things the answer did well ('you' voice).",
    )
    to_improve: list[str] = Field(
        default_factory=list,
        description="1-2 concrete, actionable things to improve ('you' voice).",
    )


class _TurnCoachingBundle(BaseModel):
    turns: list[_TurnCoachingItem] = Field(default_factory=list)


_TURN_COACHING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a supportive but honest interview coach. For EACH answered "
            "question, write short, specific feedback addressed to the candidate "
            "(use 'you'), grounded ONLY in their actual answer to that question — "
            "do not invent evidence and do not mix in other questions.\n"
            "For every question return: 1-2 concise strengths and 1-2 concrete, "
            "actionable things to improve. Every question MUST have at least one "
            "'to_improve'. If an answer is weak with no real strength, still find "
            "the most credit-worthy aspect (e.g. named a relevant tool) or return "
            "an empty strengths list — never fabricate. Keep each bullet to one "
            "short sentence.\n\n"
            "Respond with ONLY a single valid JSON object (no markdown), with key "
            '"turns": an array of objects, each with exactly these keys:\n'
            '  "index": integer (echo the question index given),\n'
            '  "strengths": array of strings,\n'
            '  "to_improve": array of strings.\n'
            "Return one object per input question, using the same index.",
        ),
        (
            "human",
            "TARGET ROLE: {job} at {company}\n\n"
            "ANSWERED QUESTIONS (index, question, the candidate's answer, and its "
            "score where available):\n{turns_json}\n\n"
            "Return the JSON object now.",
        ),
    ]
)


def generate_turn_coaching(
    profile_record: dict[str, Any],
    turns: list[dict[str, Any]],
) -> list[dict[str, list[str]]]:
    """Concise per-question strengths + improvements, aligned to ``turns`` order.

    One batched LLM call so every answered question gets candidate-facing
    feedback, even when the interview-time evaluation left the arrays sparse.
    Returns a list the same length as ``turns``; each item is
    ``{"strengths": [...], "to_improve": [...]}``.
    """
    if not turns:
        return []

    compact = [
        {
            "index": index,
            "question": str(turn.get("question") or ""),
            "answer": str(turn.get("answer") or ""),
            "score": turn.get("overall_score"),
        }
        for index, turn in enumerate(turns)
    ]
    prompt = _TURN_COACHING_PROMPT.invoke(
        {
            "job": profile_record.get("job_title") or "the role",
            "company": profile_record.get("company") or "the company",
            "turns_json": json.dumps(compact, ensure_ascii=False, indent=2),
        }
    )
    result = llm_client.call_llm_with_structured_output(prompt, _TurnCoachingBundle)
    by_index = {item.index: item for item in result.turns}

    coaching: list[dict[str, list[str]]] = []
    for index in range(len(turns)):
        item = by_index.get(index)
        coaching.append(
            {
                "strengths": [s for s in (item.strengths if item else []) if s][:3],
                "to_improve": [w for w in (item.to_improve if item else []) if w][:3],
            }
        )
    return coaching


# --- AI sample answer -------------------------------------------------------


class _SampleAnswer(BaseModel):
    sample_answer: str = Field(
        ..., description="A strong, concise STAR-style spoken answer."
    )


_SAMPLE_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert interview coach. Write a strong, realistic spoken "
            "answer to the interview question, in the first person, grounded ONLY "
            "in the candidate's actual resume. Use a STAR-style structure "
            "(situation, task, action, result) with a concrete metric where the "
            "resume supports one. Keep it 120-200 words. Do not invent facts that "
            "are not in the resume.\n\n"
            "Respond with ONLY a single valid JSON object and nothing else (no "
            'markdown), with exactly one key: "sample_answer": string.',
        ),
        (
            "human",
            "CANDIDATE RESUME (JSON):\n{resume_json}\n\n"
            "JOB DESCRIPTION:\n{job_description}\n\n"
            "INTERVIEW QUESTION:\n{question}\n\n"
            "Return the JSON object now.",
        ),
    ]
)


def generate_sample_answer(
    profile_record: dict[str, Any],
    question: str,
) -> str:
    """Generate an "AI Sample Answer" personalized to the resume."""
    resume = deps.load_resume_or_404(profile_record["resume_version"])
    jd_text = profile_record.get("job_description") or ""

    prompt = _SAMPLE_ANSWER_PROMPT.invoke(
        {
            "resume_json": _resume_to_text(resume),
            "job_description": jd_text,
            "question": question,
        }
    )
    result = llm_client.call_llm_with_structured_output(prompt, _SampleAnswer)
    return result.sample_answer


# --- Suggested bullets (lightweight, no embeddings) -------------------------


def _resume_to_text(resume: dict[str, Any]) -> str:
    import json

    return json.dumps(resume, ensure_ascii=False, indent=2)


_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) > 2}


def suggested_bullets(
    resume: dict[str, Any],
    question: str | None = None,
) -> list[dict[str, Any]]:
    """Group the resume's experience/project bullets, ranked by relevance.

    Mirrors the "Suggested Bullets" panel in the design, which simply surfaces
    the candidate's own resume bullets grouped by role. When a question is
    given, groups are ordered by keyword overlap with it (no vector store).
    """
    q_words = _keywords(question or "")

    groups: list[dict[str, Any]] = []
    for section in resume.get("sections", []):
        name = section.get("section_name")
        if name not in ("Work Experience", "Projects"):
            continue
        for item in section.get("items", []):
            bullets = [b for b in (item.get("bullets") or []) if b]
            if not bullets:
                continue
            heading = _item_heading(item)
            score = 0
            if q_words:
                joined = " ".join(bullets).lower()
                score = sum(1 for w in q_words if w in joined)
            groups.append({"heading": heading, "bullets": bullets, "_score": score})

    if q_words:
        groups.sort(key=lambda g: g["_score"], reverse=True)
    for g in groups:
        g.pop("_score", None)
    return groups


def _item_heading(item: dict[str, Any]) -> str:
    if item.get("project_name"):
        return str(item["project_name"])
    parts = [item.get("job_title"), item.get("company")]
    heading = " — ".join(p for p in parts if p)
    dates = item.get("start_date") or item.get("end_date")
    if dates:
        span = f"{item.get('start_date') or ''} – {item.get('end_date') or 'Present'}"
        heading = f"{heading} ({span})" if heading else span
    return heading or "Experience"


# --- Practice history -------------------------------------------------------


def save_practice_run(profile_id: str, run: dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    path = deps.PRACTICE_RUNS_DIR / deps.safe_id(profile_id) / f"{ts}.json"
    deps.write_json(path, run)


def list_practice_history(profile_id: str) -> list[dict[str, Any]]:
    folder = deps.PRACTICE_RUNS_DIR / deps.safe_id(profile_id)
    if not folder.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        try:
            runs.append(deps.read_json(path))
        except (ValueError, OSError):
            continue
    return runs
