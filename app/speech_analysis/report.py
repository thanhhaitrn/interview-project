"""Compact delivery payload for the LLM evaluation prompt.

Selects the most decision-relevant fluency/voice (and optional face) signals
from a transcript JSON so the evaluation prompt stays small.
"""

from __future__ import annotations

from typing import Any

_FLUENCY_KEYS = (
    "speech_rate_wpm",
    "articulation_rate_wpm",
    "pause_count",
    "long_pause_count",
    "filler_count",
    "filler_per_min",
    "repetition_count",
    "mean_length_of_run",
    "warnings",
)

_VOICE_KEYS = (
    "tremor_label",
    "tremor_indicators",
    "jitter_local_pct",
    "shimmer_local_pct",
    "f0_mean_hz",
    "f0_cv",
    "voiced_fraction",
)

_VIDEO_KEYS = (
    "face_visible_ratio",
    "camera_facing_ratio",
    "candidate_centered_ratio",
    "head_movement_amount",
    "smile_frequency",
    "happy_frame_ratio",
    "dominant_emotion_counts",
)


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys if source.get(key) is not None}


def build_delivery_metrics(
    transcript_json: dict[str, Any],
    video_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact delivery-metrics dict from a transcript JSON.

    ``video_metrics`` is the ``video_presentation`` section of a
    ``VideoAnalysisResult.to_dict()`` when face analysis is included.
    """
    delivery: dict[str, Any] = {}

    fluency = _pick(transcript_json.get("fluency"), _FLUENCY_KEYS)
    if fluency:
        delivery["fluency"] = fluency

    voice = _pick(transcript_json.get("voice"), _VOICE_KEYS)
    if voice:
        delivery["voice"] = voice

    face = _pick(video_metrics, _VIDEO_KEYS)
    if face:
        delivery["face"] = face

    return delivery
