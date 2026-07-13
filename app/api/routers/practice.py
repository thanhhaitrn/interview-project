"""Practice endpoints: questions, sample answer, suggested bullets, evaluate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api import deps
from app.api.schemas_api import (
    EvaluateRequest,
    QuestionsRequest,
    ReportRequest,
    SampleAnswerRequest,
    SampleAnswerResponse,
)
from app.api.services import practice_service

router = APIRouter(prefix="/api/practice", tags=["practice"])


def _llm_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"LLM request failed: {exc}")


@router.post("/questions")
def generate_questions(payload: QuestionsRequest) -> dict[str, Any]:
    profile = deps.load_profile_or_404(payload.profile_id)
    try:
        return practice_service.generate_questions(profile, payload.question_count)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _llm_error(exc)


@router.post("/sample-answer", response_model=SampleAnswerResponse)
def sample_answer(payload: SampleAnswerRequest) -> SampleAnswerResponse:
    profile = deps.load_profile_or_404(payload.profile_id)
    try:
        text = practice_service.generate_sample_answer(profile, payload.question)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _llm_error(exc)
    return SampleAnswerResponse(sample_answer=text)


@router.get("/suggested-bullets")
def suggested_bullets(resume_id: str, question: str | None = None) -> list[dict[str, Any]]:
    resume = deps.load_resume_or_404(resume_id)
    return practice_service.suggested_bullets(resume, question)


@router.post("/evaluate")
def evaluate(payload: EvaluateRequest) -> dict[str, Any]:
    profile = deps.load_profile_or_404(payload.profile_id)
    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is empty.")

    try:
        evaluation = practice_service.evaluate_answer(
            profile,
            question=payload.question,
            answer=payload.answer,
            expected_good_answer_points=payload.expected_good_answer_points,
            delivery_metrics=payload.delivery_metrics,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _llm_error(exc)

    if payload.save:
        practice_service.save_practice_run(
            payload.profile_id,
            {
                "profile_id": payload.profile_id,
                "question": payload.question,
                "answer": payload.answer,
                "delivery_metrics": payload.delivery_metrics,
                "evaluation": evaluation,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return evaluation


@router.post("/report")
def report(payload: ReportRequest) -> dict[str, Any]:
    profile = deps.load_profile_or_404(payload.profile_id)
    if not payload.turns:
        raise HTTPException(status_code=400, detail="No answered questions to report on.")
    turns = [t.model_dump(exclude_none=True) for t in payload.turns]
    try:
        return practice_service.generate_report(profile, turns)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _llm_error(exc)


@router.get("/history/{profile_id}")
def practice_history(profile_id: str) -> list[dict[str, Any]]:
    deps.load_profile_or_404(profile_id)
    return practice_service.list_practice_history(profile_id)
