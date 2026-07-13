"""Tests for CLI answer-mode media helpers."""

from __future__ import annotations

import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.main import (
    _choose_answer_mode,
    _collect_answer_payload,
    process_audio_answer,
    process_video_answer,
)


class AnswerModeHelperTestCase(unittest.TestCase):
    """Verify audio/video helpers build compact delivery payloads."""

    def _args(self, answer_mode: str) -> Namespace:
        return Namespace(
            answer_mode=answer_mode,
            transcription_model="tiny.en",
            transcription_language="en",
            video_sample_every_n=10,
            record_seconds=30,
            record_sample_rate=16000,
            camera_device=None,
            audio_device=None,
            keep_recordings=False,
        )

    def test_answer_mode_menu_accepts_record_choices(self):
        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            return_value="4",
        ), patch("builtins.print"):
            self.assertEqual(_choose_answer_mode("ask"), "record_audio")

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            return_value="5",
        ), patch("builtins.print"):
            self.assertEqual(_choose_answer_mode("ask"), "record_video")

        self.assertEqual(_choose_answer_mode("record-audio"), "record_audio")
        self.assertEqual(_choose_answer_mode("record-video"), "record_video")

    def test_process_audio_answer_returns_speech_metrics_only(self):
        with patch(
            "app.main._transcribe_media_answer",
            return_value=(
                "I described the backend API implementation.",
                {
                    "fluency": {"speech_rate_wpm": 130},
                    "voice": {"tremor_label": "steady"},
                },
            ),
        ):
            answer_text, delivery_metrics = process_audio_answer(
                Path("answer.wav"),
                model="tiny.en",
                language="en",
            )

        self.assertEqual(answer_text, "I described the backend API implementation.")
        self.assertEqual(delivery_metrics["fluency"]["speech_rate_wpm"], 130)
        self.assertEqual(delivery_metrics["voice"]["tremor_label"], "steady")
        self.assertNotIn("face", delivery_metrics)
        self.assertNotIn("video_quality", delivery_metrics)

    def test_process_video_answer_combines_speech_and_video_metrics(self):
        class FakeVideoResult:
            def to_dict(self):
                return {
                    "video_presentation": {
                        "face_visible_ratio": 0.92,
                        "camera_facing_ratio": 0.81,
                        "candidate_centered_ratio": 0.84,
                        "head_movement_amount": {
                            "score": 0.06,
                            "label": "moderate",
                        },
                        "emotion_analysis_available": True,
                        "happy_frame_ratio": 0.18,
                        "happy_score_mean": 28.4,
                        "smile_frequency": 0.18,
                    },
                    "video_quality": {
                        "brightness_mean": 105.0,
                        "blur_score_mean": 98.0,
                        "resolution": "1920x1080",
                        "fps": 30.0,
                        "multiple_faces_detected": False,
                    },
                    "warnings": [
                        "camera_facing_ratio_is_approximate_not_eye_contact",
                    ],
                }

        class FakeVideoAnalyzer:
            def __init__(self, config):
                self.config = config

            def analyze(self, video_path):
                return FakeVideoResult()

        with patch(
            "app.video_analysis.VideoAnalyzer",
            FakeVideoAnalyzer,
        ), patch(
            "app.main._transcribe_media_answer",
            return_value=(
                "I described the backend API implementation.",
                {
                    "fluency": {"speech_rate_wpm": 130},
                    "voice": {"tremor_label": "steady"},
                },
            ),
        ), patch("builtins.print") as fake_print:
            answer_text, delivery_metrics = process_video_answer(
                Path("answer.mp4"),
                model="tiny.en",
                language="en",
                sample_every_n=10,
            )

        printed_text = "\n".join(str(call.args[0]) for call in fake_print.call_args_list)
        self.assertEqual(answer_text, "I described the backend API implementation.")
        self.assertEqual(delivery_metrics["fluency"]["speech_rate_wpm"], 130)
        self.assertEqual(delivery_metrics["face"]["face_visible_ratio"], 0.92)
        self.assertEqual(delivery_metrics["face"]["candidate_centered_ratio"], 0.84)
        self.assertEqual(delivery_metrics["video_quality"]["resolution"], "1920x1080")
        self.assertFalse(delivery_metrics["video_quality"]["multiple_faces_detected"])
        self.assertIn("camera_facing_ratio_is_approximate_not_eye_contact", delivery_metrics["warnings"])
        self.assertIn("[VIDEO] face visible 92.0%", printed_text)
        self.assertIn("[VIDEO] emotion/happy 18.0%", printed_text)

    def test_record_audio_mode_reuses_audio_file_pipeline(self):
        recorded_path = Path("recorded_audio.wav")

        with patch(
            "app.media_recording.record_audio_answer",
            return_value=recorded_path,
        ) as fake_record, patch(
            "app.main.process_audio_answer",
            return_value=(
                "Recorded audio transcript.",
                {"fluency": {"speech_rate_wpm": 120}},
            ),
        ) as fake_process, patch("builtins.print"):
            payload = _collect_answer_payload(
                self._args("record-audio"),
                recordings_dir=Path("recordings"),
            )

        fake_record.assert_called_once_with(
            output_dir=Path("recordings"),
            duration_seconds=30,
            sample_rate=16000,
        )
        fake_process.assert_called_once_with(
            recorded_path,
            model="tiny.en",
            language="en",
        )
        self.assertEqual(payload["answer"], "Recorded audio transcript.")
        self.assertEqual(payload["answer_source"], "record_audio")
        self.assertEqual(payload["delivery_metrics"]["fluency"]["speech_rate_wpm"], 120)

    def test_record_video_mode_reuses_video_file_pipeline(self):
        recorded_path = Path("recorded_video.mp4")

        with patch(
            "app.media_recording.record_video_answer",
            return_value=recorded_path,
        ) as fake_record, patch(
            "app.main.process_video_answer",
            return_value=(
                "Recorded video transcript.",
                {
                    "fluency": {"speech_rate_wpm": 125},
                    "face": {"face_visible_ratio": 0.9},
                },
            ),
        ) as fake_process, patch("builtins.print"):
            payload = _collect_answer_payload(
                self._args("record-video"),
                recordings_dir=Path("recordings"),
            )

        fake_record.assert_called_once_with(
            output_dir=Path("recordings"),
            duration_seconds=30,
            camera_device=None,
            audio_device=None,
        )
        fake_process.assert_called_once_with(
            recorded_path,
            model="tiny.en",
            language="en",
            sample_every_n=10,
        )
        self.assertEqual(payload["answer"], "Recorded video transcript.")
        self.assertEqual(payload["answer_source"], "record_video")
        self.assertEqual(payload["delivery_metrics"]["face"]["face_visible_ratio"], 0.9)

    def test_recording_failure_is_raised_for_interview_fallback(self):
        with patch(
            "app.media_recording.record_audio_answer",
            side_effect=RuntimeError("microphone unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "microphone unavailable"):
                _collect_answer_payload(
                    self._args("record-audio"),
                    recordings_dir=Path("recordings"),
                )


if __name__ == "__main__":
    unittest.main()
