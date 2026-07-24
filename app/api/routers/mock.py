"""Mock interview endpoints driven by the LangGraph interview workflow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api import deps
from app.api.schemas_api import MockAnswerRequest, MockStartRequest
from app.api.services import mock_service

router = APIRouter(prefix="/api/mock", tags=["mock"])


@router.get("/options")
def options() -> dict[str, dict[str, str]]:
    """Interviewer personas the setup screen can offer."""
    return {
        "roles": mock_service.INTERVIEWER_ROLES,
        "styles": mock_service.INTERVIEWER_STYLES,
    }


@router.post("/start")
def start(payload: MockStartRequest) -> dict[str, Any]:
    profile = deps.load_profile_or_404(payload.profile_id)
    try:
        return mock_service.start_session(
            profile,
            question_count=payload.question_count,
            difficulty=payload.difficulty,
            interviewer_role=payload.interviewer_role,
            interviewer_style=payload.interviewer_style,
            extra_notes=payload.extra_notes,
            max_followups_per_question=payload.max_followups_per_question,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not start interview: {exc}")


@router.post("/answer")
def answer(payload: MockAnswerRequest) -> dict[str, Any]:
    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is empty.")
    try:
        return mock_service.submit_answer(
            payload.thread_id,
            payload.answer,
            answer_source=payload.answer_source,
            delivery_metrics=payload.delivery_metrics,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not submit answer: {exc}")


@router.get("/history")
def all_history() -> list[dict[str, Any]]:
    """Summaries of every saved mock interview, across all profiles."""
    return mock_service.list_all_mock_history()


@router.get("/history/{profile_id}")
def history(profile_id: str) -> list[dict[str, Any]]:
    """Summaries of a profile's past mock interviews, newest first."""
    deps.load_profile_or_404(profile_id)
    return mock_service.list_mock_history(profile_id)


@router.get("/history/{profile_id}/{run_id}")
def review(profile_id: str, run_id: str) -> dict[str, Any]:
    """The full saved review (report + per-question breakdown) for one interview."""
    deps.load_profile_or_404(profile_id)
    return mock_service.get_mock_run(profile_id, run_id)
