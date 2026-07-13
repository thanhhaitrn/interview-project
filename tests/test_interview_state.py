"""Tests for graph state and the agent compatibility facade."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import app.agent.llm_client as llm_client
from app.agent import InterviewAgent, TurnDecisionOutput, get_agent_profile
from app.graph import GraphState, merge_dicts


class InterviewGraphStateTestCase(unittest.TestCase):
    """Verify graph state and direct agent call behavior."""

    def test_graph_state_accepts_workflow_node_keys(self):
        state: GraphState = {
            "request_payload": {"interview_type": "technical"},
            "status": "pending",
            "turn_summaries": [],
            "turns": [],
            "errors": [],
        }

        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["request_payload"], {"interview_type": "technical"})
        self.assertEqual(state["turn_summaries"], [])
        self.assertEqual(state["turns"], [])
        self.assertEqual(state["errors"], [])

    def test_merge_dicts_overwrites_right_hand_values(self):
        self.assertEqual(
            merge_dicts({"score": 1, "status": "old"}, {"status": "new"}),
            {"score": 1, "status": "new"},
        )

    def test_agent_facade_generates_structured_question(self):
        agent = InterviewAgent(profile=get_agent_profile())

        def fake_structured_call(prompt, schema, **kwargs):
            return schema.model_validate(
                {
                    "interview_stage": "technical_screen",
                    "seniority_level": "junior",
                    "difficulty_level": "medium",
                    "question_count": 0,
                }
            )

        with patch(
            "app.agent.llm_client.call_llm_with_structured_output",
            side_effect=fake_structured_call,
        ):
            result = agent.generate_question_structured(
                cv_context=["Built REST APIs"],
                job_description_context=["Backend role"],
                interview_type="technical",
                difficulty="medium",
            )

        self.assertEqual(result.interview_stage, "technical_screen")

    def test_llm_client_retries_json_mode_after_parser_failure(self):
        methods = []

        class PrimaryModel:
            def with_structured_output(self, schema, method=None):
                methods.append(method)

                class StructuredModel:
                    def invoke(self, prompt, config=None):
                        raise ValueError("Invalid json output:")

                return StructuredModel()

        class RetryModel:
            def invoke(self, prompt, config=None):
                return type(
                    "Message",
                    (),
                    {
                        "content": (
                            '{"action":"next_question",'
                            '"reason":"Enough evidence to continue."}'
                        )
                    },
                )()

        models = iter([PrimaryModel(), RetryModel()])
        formats = []

        def fake_get_model(settings=None, response_format=None, temperature=None):
            formats.append(response_format)
            return next(models)

        llm_client.reset_call_trace()
        with patch(
            "app.agent.llm_client.get_model_settings",
            return_value={
                "base_url": "http://localhost:11434",
                "api_key": "",
                "model_name": "test-model",
            },
        ), patch(
            "app.agent.llm_client.get_ollama_chat_model",
            side_effect=fake_get_model,
        ):
            result = llm_client.call_llm_with_structured_output(
                "Choose next action.",
                TurnDecisionOutput,
            )

        self.assertEqual(result.action, "next_question")
        self.assertEqual(methods[0], "json_schema")
        self.assertIsNone(formats[0])
        self.assertIsInstance(formats[1], dict)
        trace = llm_client.get_call_trace()[-1]
        self.assertEqual(trace["status"], "ok")
        self.assertEqual(trace["structured_output_method"], "json_schema")
        self.assertTrue(trace["fallback_used"])
        self.assertEqual(trace["fallback_format"], "json_schema")
        self.assertIn("Invalid json output", trace["primary_error"])

    def test_llm_client_rejects_json_with_extra_text(self):
        with self.assertRaisesRegex(ValueError, "no markdown"):
            llm_client._load_json_value('Here is the JSON: {"action":"next_question"}')


if __name__ == "__main__":
    unittest.main()
