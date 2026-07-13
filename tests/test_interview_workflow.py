"""Tests for the LangGraph interview workflow."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.outputs import (
    EvaluatedAnswerOutput,
    FinalInterviewReportOutput,
    GeneratedQuestionOutput,
    TurnDecisionOutput,
    clean_empty_fields,
)
from app.agent.profile import get_agent_profile
from app.graph.nodes import ask_question_node, evaluate_answer_node, generate_plan_node
from app.graph.workflow import resume_interview, start_interview, workflow_steps


class InterviewWorkflowTestCase(unittest.TestCase):
    """Verify the graph-based workflow follows the current agent plan."""

    def test_workflow_steps_describe_current_plan(self):
        steps = workflow_steps()

        self.assertIn("Start interview", steps)
        self.assertIn("Load full JD + full resume", steps)
        self.assertIn("Candidate answers", steps)
        self.assertIn("Final report", steps)

    def test_interview_workflow_interrupts_and_resumes_to_final_report(self):
        payload = {
            "resume": {
                "sections": [
                    {
                        "section_name": "Experience",
                        "items": [{"summary": "Built REST APIs with SQL debugging."}],
                    }
                ]
            },
            "job_description": {
                "role_title": "Backend Engineer",
                "requirements": ["Build APIs", "Debug SQL performance"],
            },
            "interview_config": {"question_count": 2},
            "interview_type": "technical",
            "difficulty": "medium",
        }
        decisions = iter(["next_question", "final_report"])
        decision_prompts: list[str] = []
        checkpointer = InMemorySaver()

        def fake_structured_call(prompt, schema, **kwargs):
            if schema is GeneratedQuestionOutput:
                return schema.model_validate(
                    {
                        "interview_stage": "technical_screen",
                        "seniority_level": "junior",
                        "difficulty_level": "medium",
                        "question_count": 2,
                        "document_brief": {
                            "candidate_summary": "Backend candidate with API and SQL experience.",
                            "role_summary": "Backend Engineer role focused on APIs and SQL performance.",
                            "key_resume_evidence": ["REST API work", "SQL debugging"],
                            "key_job_requirements": ["Build APIs", "Debug SQL performance"],
                            "role_alignment_notes": ["API and SQL evidence aligns to the role."],
                            "fairness_notes": ["Score only observed evidence."],
                        },
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Describe an API you built.",
                                "competency": "API Development",
                                "technique": "project_deep_dive",
                                "difficulty": "medium",
                                "reason_for_asking": "Assess API depth.",
                                "resume_grounding": "Built REST APIs.",
                                "job_alignment": "Role requires APIs.",
                                "expected_strong_answer_signals": ["Concrete design"],
                                "red_flags": ["No details"],
                                "follow_up_questions": ["How did you test it?"],
                                "scoring_guidance": {
                                    "strong_answer": "Concrete design and tradeoffs.",
                                    "average_answer": "Basic implementation.",
                                    "weak_answer": "Vague answer.",
                                },
                            },
                            {
                                "id": "q2",
                                "question": "Tell me about a SQL performance bug.",
                                "competency": "Debugging",
                                "technique": "behavioral_star",
                                "difficulty": "medium",
                                "reason_for_asking": "Assess debugging evidence.",
                                "resume_grounding": "SQL debugging.",
                                "job_alignment": "Role requires SQL performance.",
                                "expected_strong_answer_signals": ["Diagnosis"],
                                "red_flags": ["No verification"],
                                "follow_up_questions": ["How did you prevent regression?"],
                                "scoring_guidance": {
                                    "strong_answer": "Clear diagnosis and validation.",
                                    "average_answer": "Basic fix.",
                                    "weak_answer": "No process.",
                                },
                            },
                        ],
                    }
                )

            if schema is EvaluatedAnswerOutput:
                prompt_text = prompt.to_string()
                self.assertNotIn("Resume JSON", prompt_text)
                self.assertNotIn("Job description JSON", prompt_text)
                self.assertNotIn("Delivery metrics JSON", prompt_text)
                self.assertIn("Document brief JSON", prompt_text)
                self.assertIn("Backend candidate with API and SQL experience.", prompt_text)
                self.assertIn("Question JSON", prompt_text)
                self.assertNotIn("Built REST APIs with SQL debugging.", prompt_text)
                return schema.model_validate(
                    {
                        "overall_score": 4,
                        "overall_rating": "strong",
                        "hiring_signal": "positive",
                        "confidence": "medium",
                        "summary": "Concrete answer.",
                        "criteria_scores": [
                            {
                                "criterion": "Technical Accuracy",
                                "weight": 30,
                                "score": 4,
                                "weighted_score": 1.2,
                                "reason": "Relevant technical evidence.",
                                "evidence_from_answer": ["Concrete example"],
                                "missing_evidence": [],
                                "improvement_advice": "Add metrics.",
                            }
                        ],
                    }
                )

            if schema is TurnDecisionOutput:
                prompt_text = prompt.to_string()
                decision_prompts.append(prompt_text)
                self.assertIn("Document brief JSON", prompt_text)
                self.assertIn("Debug SQL performance", prompt_text)
                self.assertIn("Current question JSON", prompt_text)
                self.assertIn("Latest evaluation JSON", prompt_text)
                self.assertNotIn('"question": {', prompt_text)
                self.assertNotIn('"evaluation": {', prompt_text)
                return schema.model_validate(
                    {
                        "action": next(decisions),
                        "reason": "Continue according to plan.",
                    }
                )

            if schema is FinalInterviewReportOutput:
                prompt_text = prompt.to_string()
                self.assertIn("Document brief JSON", prompt_text)
                self.assertIn("Backend Engineer role focused on APIs", prompt_text)
                self.assertIn("turns JSON", prompt_text)
                self.assertIn("question_text", prompt_text)
                self.assertNotIn('"question": {', prompt_text)
                return schema.model_validate(
                    {
                        "overall_recommendation": "positive",
                        "summary": "Candidate showed relevant backend evidence.",
                        "strengths": ["API development"],
                        "risks": [],
                        "evidence_highlights": ["Concrete examples"],
                        "question_summaries": [],
                        "suggested_next_steps": ["Proceed to next round"],
                    }
                )

            raise AssertionError(f"Unexpected schema: {schema}")

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            started = start_interview(
                payload,
                thread_id="test-interview-thread",
                debug_trace=True,
                checkpointer=checkpointer,
            )
            self.assertIn("__interrupt__", started)
            first_interrupt = started["__interrupt__"][0].value
            self.assertEqual(first_interrupt["question"]["id"], "q1")

            after_first_answer = resume_interview(
                thread_id="test-interview-thread",
                answer="I designed REST endpoints and tested error handling.",
                checkpointer=checkpointer,
            )
            self.assertIn("__interrupt__", after_first_answer)
            second_interrupt = after_first_answer["__interrupt__"][0].value
            self.assertEqual(second_interrupt["question"]["id"], "q2")

            final_state = resume_interview(
                thread_id="test-interview-thread",
                answer="I profiled the query, added an index, and validated latency.",
                checkpointer=checkpointer,
            )

        self.assertEqual(final_state["status"], "completed")
        final_report = final_state["final_report"]
        if hasattr(final_report, "model_dump"):
            final_report = final_report.model_dump(exclude_none=True)
        self.assertEqual(final_report["overall_recommendation"], "positive")
        self.assertEqual(len(final_state["turns"]), 2)
        self.assertEqual(len(final_state["turn_summaries"]), 2)
        self.assertEqual(
            final_state["turn_summaries"][0]["question_text"],
            "Describe an API you built.",
        )
        self.assertEqual(final_state["turn_summaries"][0]["turn_index"], 1)
        self.assertEqual(final_state["turn_summaries"][0]["question_index"], 1)
        self.assertEqual(final_state["turn_summaries"][1]["turn_index"], 2)
        self.assertEqual(final_state["turn_summaries"][1]["question_index"], 2)
        self.assertEqual(final_state["turn_summaries"][0]["decision_action"], "next_question")
        self.assertEqual(final_state["turns"][0]["routed_action"], "next_question")
        self.assertEqual(final_state["turns"][0]["question_index"], 0)
        self.assertIn("document_brief", final_state)
        self.assertEqual(
            final_state["document_brief"]["candidate_summary"],
            "Backend candidate with API and SQL experience.",
        )
        self.assertGreaterEqual(len(final_state["trace"]), 7)
        self.assertNotIn(
            "I designed REST endpoints and tested error handling.",
            decision_prompts[-1],
        )

    def test_delivery_metrics_payload_reaches_evaluation_prompt(self):
        payload = {
            "cv_context": ["Built REST APIs"],
            "job_description_context": ["Backend role requiring clear communication"],
            "interview_config": {"question_count": 1},
        }
        checkpointer = InMemorySaver()

        def fake_structured_call(prompt, schema, **kwargs):
            if schema is GeneratedQuestionOutput:
                return schema.model_validate(
                    {
                        "question_count": 1,
                        "document_brief": {
                            "candidate_summary": "Backend candidate.",
                            "role_summary": "Backend role.",
                            "key_resume_evidence": ["REST APIs"],
                            "key_job_requirements": ["Clear communication"],
                        },
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Describe an API you built.",
                                "competency": "API Development",
                                "expected_strong_answer_signals": ["Concrete details"],
                            }
                        ],
                    }
                )

            if schema is EvaluatedAnswerOutput:
                prompt_text = prompt.to_string()
                self.assertIn("Delivery metrics JSON", prompt_text)
                self.assertIn("speech_rate_wpm", prompt_text)
                self.assertIn("candidate_centered_ratio", prompt_text)
                self.assertIn("video_quality", prompt_text)
                self.assertIn("multiple_faces_detected", prompt_text)
                return schema.model_validate(
                    {
                        "overall_score": 4,
                        "summary": "Relevant answer with usable delivery data.",
                        "delivery_assessment": {
                            "fluency_rating": "fair",
                            "voice_steadiness": "steady",
                            "observations": ["Speech rate was within range."],
                            "impact_on_communication": "Delivery supported clarity.",
                        },
                    }
                )

            if schema is TurnDecisionOutput:
                return schema.model_validate(
                    {
                        "action": "final_report",
                        "reason": "Enough evidence for this one-question interview.",
                    }
                )

            if schema is FinalInterviewReportOutput:
                return schema.model_validate(
                    {
                        "overall_recommendation": "positive",
                        "summary": "Completed with delivery-aware evaluation.",
                    }
                )

            raise AssertionError(f"Unexpected schema: {schema}")

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            started = start_interview(
                payload,
                thread_id="delivery-metrics-thread",
                checkpointer=checkpointer,
            )
            self.assertIn("__interrupt__", started)
            final_state = resume_interview(
                thread_id="delivery-metrics-thread",
                answer={
                    "answer": "I built REST endpoints and explained the tradeoffs.",
                    "answer_source": "video_file",
                    "delivery_metrics": {
                        "fluency": {"speech_rate_wpm": 126, "pause_count": 2},
                        "face": {"candidate_centered_ratio": 0.92},
                        "video_quality": {
                            "brightness_mean": 104.2,
                            "multiple_faces_detected": False,
                        },
                    },
                },
                checkpointer=checkpointer,
            )

        self.assertEqual(final_state["status"], "completed")
        self.assertEqual(final_state["current_answer_source"], "video_file")
        self.assertEqual(
            final_state["turns"][0]["delivery_metrics"]["fluency"]["speech_rate_wpm"],
            126,
        )
        self.assertIn("video_quality", final_state["turns"][0]["delivery_metrics"])
        self.assertEqual(
            final_state["turn_summaries"][0]["delivery_assessment"]["fluency_rating"],
            "fair",
        )

    def test_audio_delivery_metrics_reach_evaluation_prompt_without_video(self):
        prompts: list[str] = []
        state = {
            "current_question": {
                "id": "q1",
                "question": "Describe an API you built.",
                "expected_strong_answer_signals": ["Concrete details"],
            },
            "current_answer": "I built REST endpoints and explained tradeoffs.",
            "current_delivery_metrics": {
                "fluency": {"speech_rate_wpm": 126, "pause_count": 2},
                "voice": {"tremor_label": "steady"},
            },
            "profile": get_agent_profile(),
            "document_brief": {"candidate_summary": "Backend candidate."},
            "debug_trace": True,
        }

        def fake_structured_call(prompt, schema, **kwargs):
            prompts.append(prompt.to_string())
            return schema.model_validate(
                {
                    "overall_score": 4,
                    "summary": "Audio delivery metrics were considered.",
                }
            )

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            result = evaluate_answer_node(state)

        self.assertEqual(result["latest_evaluation"]["overall_score"], 4)
        self.assertIn("Delivery metrics JSON", prompts[0])
        self.assertIn("speech_rate_wpm", prompts[0])
        self.assertIn("tremor_label", prompts[0])
        self.assertNotIn("video_quality", prompts[0])

    def test_generate_plan_assigns_missing_question_ids(self):
        state = {
            "resume_context": "{}",
            "job_description_context": "{}",
            "document_brief": {"candidate_summary": "Existing compact brief."},
            "interview_type": "technical",
            "difficulty": "medium",
            "profile": get_agent_profile(question_count=2),
        }

        def fake_structured_call(prompt, schema, **kwargs):
            if schema is GeneratedQuestionOutput:
                return schema.model_validate(
                    {
                        "question_count": 2,
                        "questions": [
                            {"question": "Describe an API you built."},
                            {"question": "Tell me about a SQL issue."},
                        ],
                    }
                )
            raise AssertionError(f"Unexpected schema: {schema}")

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            result = generate_plan_node(state)

        self.assertEqual(result["planned_questions"][0]["id"], "q1")
        self.assertEqual(result["planned_questions"][1]["id"], "q2")
        self.assertEqual(result["interview_plan"]["questions"][0]["id"], "q1")
        self.assertEqual(
            result["document_brief"]["candidate_summary"],
            "Existing compact brief.",
        )

    def test_question_limit_forces_final_report(self):
        payload = {
            "cv_context": ["Built REST APIs"],
            "job_description_context": ["Backend role requiring API debugging"],
            "interview_config": {"question_count": 1},
        }
        checkpointer = InMemorySaver()

        def fake_structured_call(prompt, schema, **kwargs):
            if schema is GeneratedQuestionOutput:
                return schema.model_validate(
                    {
                        "interview_stage": "technical_screen",
                        "seniority_level": "junior",
                        "difficulty_level": "medium",
                        "question_count": 1,
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Describe a backend API you implemented.",
                                "competency": "API Development",
                                "technique": "project_deep_dive",
                                "difficulty": "medium",
                                "reason_for_asking": "Assess implementation depth.",
                                "resume_grounding": "Built REST APIs.",
                                "job_alignment": "Role requires API work.",
                                "expected_strong_answer_signals": ["Concrete endpoint"],
                                "red_flags": ["No details"],
                                "follow_up_questions": ["How did you validate it?"],
                                "scoring_guidance": {
                                    "strong_answer": "Specific implementation.",
                                    "average_answer": "General implementation.",
                                    "weak_answer": "Vague answer.",
                                },
                            }
                        ],
                    }
                )

            if schema is EvaluatedAnswerOutput:
                return schema.model_validate({"overall_score": 3})

            if schema is TurnDecisionOutput:
                return schema.model_validate(
                    {
                        "action": "next_question",
                    }
                )

            if schema is FinalInterviewReportOutput:
                return schema.model_validate(
                    {
                        "overall_recommendation": "mixed",
                        "summary": "One-question interview completed.",
                    }
                )

            raise AssertionError(f"Unexpected schema: {schema}")

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            started = start_interview(
                payload,
                thread_id="limit-thread",
                checkpointer=checkpointer,
            )
            self.assertIn("__interrupt__", started)
            final_state = resume_interview(
                thread_id="limit-thread",
                answer="I built REST APIs.",
                checkpointer=checkpointer,
            )

        self.assertEqual(final_state["status"], "completed")
        self.assertEqual(final_state["turns"][0]["routed_action"], "final_report")
        self.assertEqual(
            final_state["latest_decision"]["reason"],
            "No planned questions remain, so the workflow created the final report.",
        )

    def test_ask_question_uses_plan_and_prioritizes_pending_followup(self):
        state = {
            "debug_trace": True,
            "planned_questions": [
                {
                    "id": "q1",
                    "question": "Describe a backend API you implemented.",
                    "competency": "API Development",
                }
            ],
            "current_question_index": 0,
            "pending_followup_question": "What metric changed after your fix?",
        }

        with patch(
            "app.graph.nodes.interrupt",
            return_value={"answer": "Latency improved by 20%."},
        ) as fake_interrupt, patch(
            "app.graph.nodes.llm_client.call_llm_with_structured_output",
            side_effect=AssertionError("ask_question_node must not call the LLM."),
        ):
            result = ask_question_node(state)

        interrupt_payload = fake_interrupt.call_args.args[0]
        asked_question = interrupt_payload["question"]

        self.assertEqual(
            asked_question["question"],
            "What metric changed after your fix?",
        )
        self.assertEqual(asked_question["parent_question_id"], "q1")
        self.assertTrue(asked_question["is_follow_up"])
        self.assertEqual(asked_question["competency"], "API Development")
        self.assertEqual(result["current_answer"], "Latency improved by 20%.")
        self.assertEqual(result["current_question"], asked_question)
        self.assertEqual(result["last_node"], "ask_question")
        self.assertEqual(result["trace"][0]["node"], "ask_followup_question")
        self.assertEqual(
            result["trace"][0]["message"],
            "Received candidate answer for follow-up question.",
        )

    def test_ask_question_trace_keeps_base_question_label(self):
        state = {
            "debug_trace": True,
            "planned_questions": [
                {
                    "id": "q1",
                    "question": "Describe a backend API you implemented.",
                    "competency": "API Development",
                }
            ],
            "current_question_index": 0,
            "pending_followup_question": None,
        }

        with patch(
            "app.graph.nodes.interrupt",
            return_value={"answer": "I built REST endpoints."},
        ):
            result = ask_question_node(state)

        self.assertEqual(result["last_node"], "ask_question")
        self.assertEqual(result["trace"][0]["node"], "ask_question")
        self.assertEqual(result["trace"][0]["message"], "Received candidate answer.")

    def test_followup_is_generated_after_answer_and_limited_to_one(self):
        payload = {
            "cv_context": ["Built REST APIs"],
            "job_description_context": ["Backend role requiring API debugging"],
            "interview_config": {"question_count": 1},
            "max_followups_per_question": 2,
        }
        decisions = iter(
            [
                {
                    "action": "follow_up",
                    "reason": "Answer needs measurable evidence.",
                    "follow_up_question": "What metric changed after your fix?",
                },
                {
                    "action": "follow_up",
                    "reason": "Model asked again, but the follow-up limit is reached.",
                    "follow_up_question": "This second follow-up should not be asked.",
                },
            ]
        )
        checkpointer = InMemorySaver()

        def fake_structured_call(prompt, schema, **kwargs):
            if schema is GeneratedQuestionOutput:
                return schema.model_validate(
                    {
                        "question_count": 1,
                        "questions": [
                            {
                                "id": "q1",
                                "question": "Describe a backend API you implemented.",
                                "competency": "API Development",
                                "technique": "project_deep_dive",
                                "difficulty": "medium",
                                "reason_for_asking": "Assess implementation depth.",
                                "resume_grounding": "Built REST APIs.",
                                "job_alignment": "Role requires API work.",
                                "expected_strong_answer_signals": ["Concrete endpoint"],
                                "red_flags": ["No details"],
                                "follow_up_questions": ["Pre-generated follow-up"],
                            }
                        ],
                    }
                )

            if schema is EvaluatedAnswerOutput:
                return schema.model_validate({"overall_score": 2})

            if schema is TurnDecisionOutput:
                return schema.model_validate(next(decisions))

            if schema is FinalInterviewReportOutput:
                return schema.model_validate(
                    {
                        "overall_recommendation": "mixed",
                        "summary": "Follow-up limit enforced.",
                    }
                )

            raise AssertionError(f"Unexpected schema: {schema}")

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            started = start_interview(
                payload,
                thread_id="dynamic-followup-thread",
                checkpointer=checkpointer,
            )
            first_interrupt = started["__interrupt__"][0].value
            self.assertNotIn("follow_up_questions", first_interrupt["question"])

            after_first_answer = resume_interview(
                thread_id="dynamic-followup-thread",
                answer="I built an API.",
                checkpointer=checkpointer,
            )
            followup_interrupt = after_first_answer["__interrupt__"][0].value
            self.assertEqual(
                followup_interrupt["question"]["question"],
                "What metric changed after your fix?",
            )
            self.assertTrue(followup_interrupt["question"]["is_follow_up"])

            final_state = resume_interview(
                thread_id="dynamic-followup-thread",
                answer="Latency improved by 20%.",
                checkpointer=checkpointer,
            )

        self.assertEqual(final_state["status"], "completed")
        self.assertEqual(len(final_state["turns"]), 2)
        self.assertEqual(final_state["turn_summaries"][0]["turn_index"], 1)
        self.assertEqual(final_state["turn_summaries"][0]["question_index"], 1)
        self.assertEqual(final_state["turn_summaries"][1]["turn_index"], 2)
        self.assertEqual(final_state["turn_summaries"][1]["question_index"], 1)
        self.assertTrue(final_state["turn_summaries"][1]["is_follow_up"])
        self.assertEqual(final_state["turns"][0]["routed_action"], "follow_up")
        self.assertEqual(final_state["turns"][1]["routed_action"], "final_report")

    def test_final_report_accepts_common_llm_aliases(self):
        report = FinalInterviewReportOutput.model_validate(
            {
                "candidate_name": None,
                "strengths": ["Clear communication"],
                "risks": ["Limited technical depth"],
                "evidence": [
                    {
                        "question": "Project deep dive",
                        "overall_score": 3.8,
                        "strengths_cited": ["Quantified outcome"],
                        "weaknesses_cited": ["Limited validation detail"],
                    }
                ],
                "recommendation": "Do not advance to the next interview stage.",
                "next_steps": ["Notify candidate with constructive feedback."],
            }
        )

        self.assertEqual(
            report.overall_recommendation,
            "Do not advance to the next interview stage.",
        )
        self.assertEqual(
            report.suggested_next_steps,
            ["Notify candidate with constructive feedback."],
        )
        self.assertEqual(report.question_summaries[0]["question"], "Project deep dive")
        self.assertIn("Project deep dive", report.evidence_highlights[0])

    def test_evaluation_scores_use_single_canonical_schema(self):
        evaluation = EvaluatedAnswerOutput.model_validate(
            {
                "overall_score": 2,
                "criterion_scores": [
                    {
                        "name": "Technical Accuracy",
                        "score": 2,
                        "justification": "Answer is relevant but shallow.",
                    }
                ],
                "feedback": "Needs more technical detail.",
            }
        )
        dumped = evaluation.model_dump(exclude_none=True)

        self.assertEqual(evaluation.summary, "Needs more technical detail.")
        self.assertEqual(
            evaluation.criteria_scores[0].criterion,
            "Technical Accuracy",
        )
        self.assertEqual(
            evaluation.criteria_scores[0].reason,
            "Answer is relevant but shallow.",
        )
        self.assertIn("criteria_scores", dumped)
        self.assertNotIn("criterion_scores", dumped)
        self.assertNotIn("scores", dumped)
        self.assertNotIn("feedback", dumped)

        evaluation = EvaluatedAnswerOutput.model_validate(
            {
                "overall_score": 4,
                "scores": [
                    {
                        "name": "Specific Evidence",
                        "score": 4,
                        "evidence": "Provides a concrete metric.",
                    }
                ],
                "comments": "Strong enough evidence.",
            }
        )

        self.assertEqual(evaluation.summary, "Strong enough evidence.")
        self.assertEqual(evaluation.criteria_scores[0].criterion, "Specific Evidence")
        self.assertEqual(
            evaluation.criteria_scores[0].evidence_from_answer,
            ["Provides a concrete metric."],
        )

        evaluation = EvaluatedAnswerOutput.model_validate(
            {
                "overall_score": 3,
                "scores": {
                    "Technical Accuracy": 3,
                    "Specific Evidence": 2,
                },
                "evidence": {
                    "Technical Accuracy": "Uses relevant SQL and validation checks.",
                    "Specific Evidence": "Examples are relevant but not specific enough.",
                },
                "feedback": "Good tool familiarity, but needs more concrete results.",
            }
        )

        self.assertEqual(
            evaluation.summary,
            "Good tool familiarity, but needs more concrete results.",
        )
        self.assertEqual(evaluation.criteria_scores[0].criterion, "Technical Accuracy")
        self.assertEqual(evaluation.criteria_scores[0].score, 3)
        self.assertEqual(
            evaluation.criteria_scores[0].reason,
            "Uses relevant SQL and validation checks.",
        )

    def test_turn_decision_accepts_reason_aliases(self):
        decision = TurnDecisionOutput.model_validate(
            {
                "action": "follow_up",
                "rationale": "Answer lacks measurable evidence.",
                "follow_up_question": "What metric changed?",
            }
        )

        self.assertEqual(decision.reason, "Answer lacks measurable evidence.")

    def test_clean_empty_fields_removes_blank_output_values(self):
        cleaned = clean_empty_fields(
            {
                "summary": "",
                "strengths": [],
                "score": 0,
                "nested": {
                    "reason": "  useful reason  ",
                    "notes": [],
                },
                "items": ["kept", "", {}, []],
            }
        )

        self.assertNotIn("summary", cleaned)
        self.assertNotIn("strengths", cleaned)
        self.assertEqual(cleaned["score"], 0)
        self.assertEqual(cleaned["nested"], {"reason": "useful reason"})
        self.assertEqual(cleaned["items"], ["kept"])


if __name__ == "__main__":
    unittest.main()
