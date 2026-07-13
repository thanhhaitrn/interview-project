"""Unit tests for interview config wiring and prompt constraints."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.agent import get_agent_profile
from app.agent.prompts import (
    build_evaluation_prompt,
    build_question_prompt,
    build_turn_decision_chat_prompt,
)
from app.agent.profile import (
    build_evaluation_profile,
    build_question_profile,
)
from app.graph.schemas import EvaluationRequest, QuestionRequest


class InterviewConfigTestCase(unittest.TestCase):
    """Verify config mapping and structured prompt design requirements."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.fixtures_dir = cls.project_root / "tests" / "fixtures"

    def test_question_profile_loads_rich_config(self):
        payload = json.loads(
            (self.fixtures_dir / "question_request.json").read_text(encoding="utf-8")
        )
        request = QuestionRequest.model_validate(payload)
        profile = build_question_profile(request)

        self.assertEqual(profile["interview_stage"], "technical_screen")
        self.assertEqual(profile["seniority_level"], "junior")
        self.assertEqual(profile["question_count"], 6)
        self.assertIn("situational", profile["question_techniques"])
        self.assertFalse(profile["question_constraints"]["require_followups"])
        self.assertTrue(profile["question_constraints"]["allow_dynamic_followups"])
        self.assertEqual(profile["max_followups_per_question"], 1)

    def test_question_profile_leaves_optional_levels_unset_without_config(self):
        request = QuestionRequest.model_validate(
            {
                "cv_context": ["Built REST APIs"],
                "job_description_context": ["Backend role requiring API work"],
            }
        )
        profile = build_question_profile(request)

        self.assertIsNone(profile["seniority_level"])
        self.assertIsNone(profile["difficulty_level"])
        self.assertEqual(profile["question_count"], get_agent_profile()["question_count"])

    def test_evaluation_profile_loads_rich_config(self):
        payload = json.loads(
            (self.fixtures_dir / "evaluation_request.json").read_text(encoding="utf-8")
        )
        request = EvaluationRequest.model_validate(payload)
        profile = build_evaluation_profile(request)

        self.assertEqual(profile["evaluation_mode"], "coaching")
        self.assertEqual(profile["scale"], "1-5")
        self.assertTrue(profile["evidence_required"])
        self.assertIn("1", profile["rating_anchors"])
        self.assertGreaterEqual(len(profile["rubric"]), 5)

    def test_question_prompt_contains_required_sections(self):
        prompt = build_question_prompt(
            cv_context=["Built REST APIs", "Used SQL and debugging workflows"],
            job_description_context=["Junior backend role", "Requires API and SQL fundamentals"],
            interview_type="technical",
            difficulty="medium",
            profile=get_agent_profile(),
        )

        self.assertIn("You are Structured interview designer", prompt)
        self.assertIn("Resume JSON", prompt)
        self.assertIn("Job description JSON", prompt)
        self.assertIn("Interview config JSON", prompt)
        self.assertIn("infer the", prompt)
        self.assertIn("Do not leave output fields blank", prompt)
        self.assertIn("Do not pre-generate follow-up questions", prompt)
        self.assertIn("max_followups_per_question", prompt)
        self.assertIn("prefer_balanced_coverage", prompt)
        self.assertIn("project_deep_dive", prompt)
        self.assertIn("Deeply examine a real project", prompt)
        self.assertIn("behavioral_star", prompt)
        self.assertIn("Situation, Task, Action, Result", prompt)
        self.assertIn("coverage_summary", prompt)
        self.assertIn("document_brief", prompt)
        self.assertIn("candidate evidence", prompt)
        self.assertIn("GeneratedQuestionOutput", prompt)
        self.assertIn('"expected_strong_answer_signals"', prompt)
        self.assertIn("Task:", prompt)

    def test_evaluation_prompt_contains_rubric_and_evidence_rules(self):
        prompt = build_evaluation_prompt(
            cv_context=["Implemented backend APIs in Python"],
            job_description_context=["Role requires API debugging and communication"],
            question="Tell me about a backend incident you resolved.",
            expected_good_answer_points=["Incident", "Diagnosis", "Fix", "Outcome"],
            student_answer="I investigated logs, identified a query bottleneck, and improved latency.",
            profile=get_agent_profile(),
            document_brief={
                "candidate_summary": "Backend candidate with Python API evidence.",
                "key_job_requirements": ["API debugging", "communication"],
            },
        )

        self.assertIn("Evaluation config JSON", prompt)
        self.assertIn("Document brief JSON", prompt)
        self.assertIn("Backend candidate with Python API evidence.", prompt)
        self.assertIn("Rubric JSON", prompt)
        self.assertIn("Rating anchors JSON", prompt)
        self.assertIn("Score only observed answer evidence", prompt)
        self.assertIn("EvaluatedAnswerOutput", prompt)
        self.assertIn("Candidate answer", prompt)

    def test_evaluation_prompt_includes_video_delivery_metrics_when_provided(self):
        prompt = build_evaluation_prompt(
            cv_context=["Implemented backend APIs in Python"],
            job_description_context=["Role requires API debugging and communication"],
            question="Tell me about a backend incident you resolved.",
            expected_good_answer_points=["Incident", "Diagnosis", "Fix", "Outcome"],
            student_answer="I investigated logs and improved latency.",
            profile=get_agent_profile(),
            delivery_metrics={
                "fluency": {"speech_rate_wpm": 126},
                "face": {"face_visible_ratio": 0.92, "candidate_centered_ratio": 0.84},
                "video_quality": {
                    "brightness_mean": 105.0,
                    "blur_score_mean": 98.0,
                    "multiple_faces_detected": False,
                },
            },
        )

        self.assertIn("Delivery metrics JSON", prompt)
        self.assertIn("speech_rate_wpm", prompt)
        self.assertIn("face_visible_ratio", prompt)
        self.assertIn("video_quality", prompt)
        self.assertIn("multiple_faces_detected", prompt)
        self.assertIn("video presentation metrics", prompt)

    def test_turn_decision_prompt_requires_one_integrated_followup(self):
        prompt = build_turn_decision_chat_prompt(
            profile=get_agent_profile(),
            document_brief={
                "candidate_summary": "Backend candidate.",
                "key_job_requirements": ["API implementation depth"],
            },
            current_question={
                "id": "q1",
                "question": "Describe an API you built.",
                "competency": "API Development",
            },
            current_answer="I built a REST API.",
            latest_evaluation={
                "overall_score": 2,
                "summary": "Missing implementation details and metrics.",
            },
            turns=[],
            current_question_index=0,
            planned_question_count=2,
            max_questions=2,
            current_followup_count=0,
            max_followups_per_question=1,
        ).to_string()

        self.assertIn("one integrated question", prompt)
        self.assertIn("Document brief JSON", prompt)
        self.assertIn("API implementation depth", prompt)
        self.assertIn("most important missing evidence", prompt)
        self.assertIn("multiple independent questions", prompt)
        self.assertIn("multiple question marks", prompt)
        self.assertIn("answer-aware, integrated follow_up_question", prompt)


if __name__ == "__main__":
    unittest.main()
