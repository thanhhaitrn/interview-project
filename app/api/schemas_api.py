"""Pydantic request/response models for the web API layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Resumes ----------------------------------------------------------------


class ResumeSummary(BaseModel):
    id: str
    full_name: str | None = None
    headline: str | None = None


# --- Profiles ---------------------------------------------------------------


class ProfileIn(BaseModel):
    """Payload to create or update an interview profile."""

    profile_id: str = Field(..., description="Unique, memorable id for the profile.")
    job_title: str | None = None
    company: str | None = None
    resume_version: str = Field(..., description="Resume id this profile uses.")
    job_description: str = Field(..., description="Full job description text.")


class Profile(ProfileIn):
    created_at: str | None = None
    updated_at: str | None = None


# --- Practice ---------------------------------------------------------------


class QuestionsRequest(BaseModel):
    profile_id: str
    question_count: int | None = Field(
        default=None, description="Override number of questions (defaults to profile)."
    )


class SampleAnswerRequest(BaseModel):
    profile_id: str
    question: str


class SampleAnswerResponse(BaseModel):
    sample_answer: str


class EvaluateRequest(BaseModel):
    profile_id: str
    question: str
    answer: str
    expected_good_answer_points: list[str] = Field(default_factory=list)
    delivery_metrics: dict[str, Any] | None = None
    save: bool = True


class SuggestedBulletGroup(BaseModel):
    heading: str
    bullets: list[str] = Field(default_factory=list)


class ReportTurn(BaseModel):
    """One answered question from a practice session, for the final report."""

    question: str
    answer: str
    overall_score: float | None = None
    hiring_signal: str | None = None
    summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class ReportRequest(BaseModel):
    profile_id: str
    turns: list[ReportTurn] = Field(default_factory=list)


# --- Media ------------------------------------------------------------------


class TranscribeResponse(BaseModel):
    text: str
    fluency: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    delivery_metrics: dict[str, Any] | None = None
