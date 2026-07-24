"""Realistic mock interview: a thin web layer over the LangGraph workflow.

Unlike practice mode (which generates all questions up front and lets the user
answer at their own pace), a mock interview is driven by the interview graph:
it asks one question, waits at an ``interrupt`` for the answer, evaluates it,
then decides whether to follow up, move on, or write the final report. Because
each answer is judged immediately, the interviewer can ask adaptive follow-up
questions based on how the answer scored.

Graph state is held by the workflow's module-level ``InMemorySaver``, keyed by
``thread_id``, so it survives across HTTP requests in the same server process.

When an interview completes, the review (coaching report + per-question
breakdown) is saved to ``data/mock_runs/<profile_id>/<run_id>.json`` so it can
be read back later from the review history pages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.api import deps
from app.graph.workflow import resume_interview, start_interview

# thread_id -> session record (profile + interviewer persona), so the closing
# report and saved review know the target role. Scoped to the process, matching
# the workflow's in-memory checkpointer.
_SESSIONS: dict[str, dict[str, Any]] = {}

INTERVIEWER_ROLES = {
    "senior_engineer": "Senior engineer (technical)",
    "hiring_manager": "Hiring manager",
    "recruiter": "Recruiter (screening)",
    "peer": "Peer teammate",
}

INTERVIEWER_STYLES = {
    "balanced": "Balanced — neutral but probing",
    "friendly": "Friendly — warm and encouraging",
    "challenging": "Challenging — pushes hard on details",
    "formal": "Formal — structured and concise",
}


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _interrupt_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the pending question out of the graph's interrupt, if any."""
    interrupts = state.get("__interrupt__")
    if not interrupts:
        return None

    interrupt = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    value = getattr(interrupt, "value", interrupt)
    return value if isinstance(value, dict) else {"value": value}


def _persona_context(
    interviewer_role: str | None,
    interviewer_style: str | None,
    extra_notes: str | None,
) -> str | None:
    """Describe the interviewer so generated questions match the persona."""
    lines: list[str] = []
    if interviewer_role:
        lines.append(f"- Role: {INTERVIEWER_ROLES.get(interviewer_role, interviewer_role)}")
    if interviewer_style:
        lines.append(f"- Style: {INTERVIEWER_STYLES.get(interviewer_style, interviewer_style)}")
    if extra_notes and extra_notes.strip():
        lines.append(f"- Notes: {extra_notes.strip()}")

    if not lines:
        return None

    return (
        "INTERVIEWER PERSONA (shape the tone and depth of the questions to "
        "match this interviewer; do not change what is being assessed):\n"
        + "\n".join(lines)
    )


def _short(text: Any, max_chars: int = 220) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _take(values: list[Any], limit: int = 3) -> list[str]:
    """Short, deduped, capped list of feedback bullets."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _short(value)
        if text and text.lower() not in seen:
            out.append(text)
            seen.add(text.lower())
        if len(out) >= limit:
            break
    return out


def _derive_strengths(evaluation: dict[str, Any]) -> list[str]:
    """What went well, falling back to strongly-scored rubric criteria."""
    values = [s for s in (evaluation.get("strengths") or []) if s]
    if not values:
        for score in evaluation.get("criteria_scores") or []:
            if not isinstance(score, dict):
                continue
            try:
                numeric = float(score.get("score"))
            except (TypeError, ValueError):
                numeric = 0.0
            reason = score.get("reason")
            if numeric >= 4 and reason:
                values.append(f"{score.get('criterion', '')}: {reason}".strip(" :"))
    return _take(values)


def _derive_improvements(evaluation: dict[str, Any]) -> list[str]:
    """What to improve, falling back to rubric advice / coaching when needed."""
    values = [w for w in (evaluation.get("weaknesses") or []) if w]
    values += [r for r in (evaluation.get("red_flags") or []) if r]
    if not values:
        for score in evaluation.get("criteria_scores") or []:
            if not isinstance(score, dict):
                continue
            if score.get("improvement_advice"):
                values.append(score["improvement_advice"])
            values += [m for m in (score.get("missing_evidence") or []) if m]
    if not values:
        coaching = evaluation.get("candidate_coaching")
        if isinstance(coaching, dict) and coaching.get("better_answer_strategy"):
            values.append(coaching["better_answer_strategy"])
    return _take(values)


def _turn_review_from_full(turn: dict[str, Any]) -> dict[str, Any] | None:
    """Build one review record from a full graph turn (complete evaluation)."""
    if not isinstance(turn, dict):
        return None
    question = turn.get("question") if isinstance(turn.get("question"), dict) else {}
    evaluation = turn.get("evaluation") if isinstance(turn.get("evaluation"), dict) else {}

    q_text = str(question.get("question") or "").strip()
    answer = str(turn.get("answer") or "").strip()
    if not q_text or not answer:
        return None

    review: dict[str, Any] = {"question": q_text, "answer": answer}
    if question.get("competency"):
        review["competency"] = question["competency"]
    if question.get("is_follow_up"):
        review["is_follow_up"] = True

    if evaluation.get("overall_score") is not None:
        review["overall_score"] = evaluation["overall_score"]
    if evaluation.get("hiring_signal"):
        review["hiring_signal"] = evaluation["hiring_signal"]
    if evaluation.get("summary"):
        review["summary"] = str(evaluation["summary"])

    strengths = _derive_strengths(evaluation)
    if strengths:
        review["strengths"] = strengths
    improvements = _derive_improvements(evaluation)
    if improvements:
        review["weaknesses"] = improvements

    delivery = evaluation.get("delivery_assessment")
    if isinstance(delivery, dict) and delivery:
        review["delivery_assessment"] = delivery

    return review


def _review_turns_compact(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Fallback: build review records from the token-compacted turn memory."""
    planned = state.get("planned_questions") or []
    competency_by_id = {
        str(question.get("id")): question.get("competency")
        for question in planned
        if isinstance(question, dict) and question.get("id")
    }

    turns: list[dict[str, Any]] = []
    for turn in state.get("turn_summaries") or []:
        if not isinstance(turn, dict):
            continue
        question = str(turn.get("question_text") or "").strip()
        answer = str(turn.get("answer") or "").strip()
        if not question or not answer:
            continue

        review: dict[str, Any] = {"question": question, "answer": answer}
        question_id = str(
            turn.get("parent_question_id") or turn.get("question_id") or ""
        )
        competency = competency_by_id.get(question_id)
        if competency:
            review["competency"] = competency
        if turn.get("is_follow_up"):
            review["is_follow_up"] = True
        if turn.get("overall_score") is not None:
            review["overall_score"] = turn["overall_score"]
        if turn.get("hiring_signal"):
            review["hiring_signal"] = turn["hiring_signal"]
        if turn.get("evaluation_summary"):
            review["summary"] = turn["evaluation_summary"]
        for key in ("strengths", "weaknesses"):
            values = turn.get(key)
            if values:
                review[key] = _take([str(value) for value in values if value])
        delivery = turn.get("delivery_assessment")
        if isinstance(delivery, dict) and delivery:
            review["delivery_assessment"] = delivery
        turns.append(review)
    return turns


def _review_turns(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-question breakdown for the review + coaching-report input.

    Prefers the graph's full ``turns`` (complete evaluations, so every turn
    reliably has strengths / improvements / delivery), and falls back to the
    token-compacted ``turn_summaries`` when the full turns are unavailable.
    Follow-up turns are marked so the UI can nest them under their question.
    """
    full_turns = state.get("turns") or []
    if full_turns:
        reviews = [_turn_review_from_full(turn) for turn in full_turns]
        reviews = [review for review in reviews if review]
        if reviews:
            return reviews
    return _review_turns_compact(state)


def _fallback_report(final_report: dict[str, Any]) -> dict[str, Any]:
    """Reframe the graph's interviewer-facing report as candidate coaching."""
    return {
        "overall_summary": final_report.get("summary"),
        "readiness": final_report.get("overall_recommendation"),
        "top_strengths": final_report.get("strengths") or [],
        "areas_to_improve": final_report.get("risks") or [],
        "action_items": final_report.get("suggested_next_steps") or [],
        "focus_next": None,
    }


def _apply_turn_coaching(
    turns: list[dict[str, Any]],
    profile_record: dict[str, Any] | None,
) -> None:
    """Fill each turn with candidate-facing strengths + to-improve.

    So every question in the breakdown has general feedback (not just the
    delivery block). Best-effort: on failure, the interview-time strengths /
    weaknesses already on each turn are kept.
    """
    if not profile_record or not turns:
        return

    from app.api.services import practice_service

    try:
        coaching = practice_service.generate_turn_coaching(profile_record, turns)
    except Exception:  # noqa: BLE001 - keep the derived feedback on failure
        return

    for turn, coach in zip(turns, coaching):
        strengths = coach.get("strengths")
        improvements = coach.get("to_improve")
        if strengths:
            turn["strengths"] = strengths
        if improvements:
            turn["weaknesses"] = improvements


def _coaching_report(
    turns: list[dict[str, Any]],
    final_report: dict[str, Any],
    profile_record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the candidate-facing report shown when the interview ends.

    Prefers the same improvement-focused report practice mode produces (built
    from the interview's turns), and falls back to reframing the graph's own
    interviewer-facing report if that call fails.
    """
    from app.api.services import practice_service

    if profile_record and turns:
        try:
            return practice_service.generate_report(profile_record, turns)
        except Exception:  # noqa: BLE001 - fall back rather than lose the report
            pass

    return _fallback_report(final_report)


def _session_view(
    state: dict[str, Any],
    thread_id: str,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize graph state into what the mock interview UI needs."""
    final_report = _model_dump(state.get("final_report"))
    done = bool(final_report) or state.get("status") == "completed"

    payload = _interrupt_payload(state) or {}
    question = payload.get("question") or state.get("current_question") or {}
    question = _model_dump(question)

    planned = state.get("planned_questions") or []

    view: dict[str, Any] = {
        "thread_id": thread_id,
        "status": str(state.get("status") or ""),
        "done": done,
        "question_index": int(state.get("current_question_index") or 0),
        "total_questions": len(planned),
    }

    if not done and question:
        view["question"] = {
            "id": question.get("id"),
            "question": question.get("question"),
            "competency": question.get("competency"),
            "technique": question.get("technique"),
            "difficulty": question.get("difficulty"),
            "is_follow_up": bool(question.get("is_follow_up")),
        }

    if done and final_report:
        profile_record = (session or {}).get("profile")
        turns = _review_turns(state)
        _apply_turn_coaching(turns, profile_record)
        report = _coaching_report(turns, final_report, profile_record)
        view["report"] = report

        # Persist the review so it can be reopened from the history pages.
        if profile_record:
            run = _build_run_record(
                session or {}, report, turns, planned_count=len(planned)
            )
            save_mock_run(profile_record["profile_id"], run)
            view["run_id"] = run["run_id"]

    return view


def start_session(
    profile_record: dict[str, Any],
    *,
    question_count: int | None = None,
    difficulty: str | None = None,
    interviewer_role: str | None = None,
    interviewer_style: str | None = None,
    extra_notes: str | None = None,
    max_followups_per_question: int = 1,
) -> dict[str, Any]:
    """Start a mock interview and return the first question."""
    resume = deps.load_resume_or_404(profile_record["resume_version"])
    jd_text = profile_record.get("job_description") or ""

    job_context = [jd_text]
    persona = _persona_context(interviewer_role, interviewer_style, extra_notes)
    if persona:
        job_context.append(persona)

    interview_config: dict[str, Any] = {}
    if question_count is not None:
        interview_config["question_count"] = question_count
    if difficulty:
        interview_config["difficulty_level"] = difficulty

    request_payload: dict[str, Any] = {
        "resume": resume,
        "job_description_context": job_context,
        "interview_type": "technical",
        "interview_config": interview_config,
        "max_followups_per_question": max(0, max_followups_per_question),
    }
    if difficulty:
        request_payload["difficulty"] = difficulty

    thread_id = str(uuid4())
    state = start_interview(request_payload, thread_id=thread_id)
    # Remember the profile + persona for this thread so the closing report and
    # the saved review know the target role (state is per-process/in-memory).
    session = {
        "profile": profile_record,
        "interviewer_role": interviewer_role,
        "interviewer_style": interviewer_style,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _SESSIONS[thread_id] = session
    return _session_view(state, thread_id, session)


def submit_answer(
    thread_id: str,
    answer: str,
    *,
    answer_source: str = "text",
    delivery_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one answer to the running interview and return the next step.

    The answer is evaluated immediately, which is what lets the graph decide
    whether to ask an adaptive follow-up before moving to the next question.
    """
    payload: dict[str, Any] = {"answer": answer, "answer_source": answer_source}
    if delivery_metrics:
        payload["delivery_metrics"] = delivery_metrics

    state = resume_interview(thread_id=thread_id, answer=payload)
    session = _SESSIONS.get(thread_id)
    view = _session_view(state, thread_id, session)
    if view["done"]:
        _SESSIONS.pop(thread_id, None)
    return view


# --- Review history ---------------------------------------------------------


def _average_score(turns: list[dict[str, Any]]) -> float | None:
    scores = [
        float(turn["overall_score"])
        for turn in turns
        if isinstance(turn.get("overall_score"), (int, float))
    ]
    return round(mean(scores), 2) if scores else None


def _build_run_record(
    session: dict[str, Any],
    report: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    planned_count: int = 0,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    profile = session.get("profile") or {}
    base_questions = sum(1 for turn in turns if not turn.get("is_follow_up"))
    return {
        "run_id": now.strftime("%Y%m%d_%H%M%S_%f"),
        "profile_id": profile.get("profile_id"),
        "job_title": profile.get("job_title"),
        "company": profile.get("company"),
        "interviewer_role": session.get("interviewer_role"),
        "interviewer_style": session.get("interviewer_style"),
        # Number of turns shown in the breakdown (base questions + follow-ups).
        "question_count": len(turns),
        "base_question_count": base_questions,
        "planned_question_count": planned_count,
        "average_score": _average_score(turns),
        "created_at": now.isoformat(),
        "report": report,
        "turns": turns,
    }


def save_mock_run(profile_id: str, run: dict[str, Any]) -> None:
    run_id = run.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run["run_id"] = run_id
    path = deps.MOCK_RUNS_DIR / deps.safe_id(profile_id) / f"{deps.safe_id(run_id)}.json"
    deps.write_json(path, run)


def _run_summary(run: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    report = run.get("report") or {}
    return {
        "run_id": run.get("run_id") or fallback_id,
        "profile_id": run.get("profile_id"),
        "job_title": run.get("job_title"),
        "company": run.get("company"),
        "interviewer_role": run.get("interviewer_role"),
        "interviewer_style": run.get("interviewer_style"),
        "question_count": run.get("question_count"),
        "average_score": run.get("average_score"),
        "readiness": report.get("readiness"),
        "created_at": run.get("created_at"),
    }


def list_mock_history(profile_id: str) -> list[dict[str, Any]]:
    """Lightweight summaries of a profile's past mock interviews, newest first."""
    folder = deps.MOCK_RUNS_DIR / deps.safe_id(profile_id)
    if not folder.exists():
        return []

    summaries: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        try:
            run = deps.read_json(path)
        except (ValueError, OSError):
            continue
        summaries.append(_run_summary(run, path.stem))
    return summaries


def list_all_mock_history() -> list[dict[str, Any]]:
    """Summaries of every saved mock interview across all profiles, newest first."""
    if not deps.MOCK_RUNS_DIR.exists():
        return []

    summaries: list[dict[str, Any]] = []
    for folder in deps.MOCK_RUNS_DIR.iterdir():
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            try:
                run = deps.read_json(path)
            except (ValueError, OSError):
                continue
            summary = _run_summary(run, path.stem)
            summary.setdefault("profile_id", folder.name)
            if not summary.get("profile_id"):
                summary["profile_id"] = folder.name
            summaries.append(summary)

    summaries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return summaries


def get_mock_run(profile_id: str, run_id: str) -> dict[str, Any]:
    path = deps.MOCK_RUNS_DIR / deps.safe_id(profile_id) / f"{deps.safe_id(run_id)}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Review not found: {run_id}")
    return deps.read_json(path)
