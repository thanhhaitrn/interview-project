"""Result schemas and configuration for lightweight video analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class VideoAnalysisConfig:
    """Settings that control video sampling, thresholds, and optional emotion analysis."""

    sample_every_n: int = 10
    min_face_size: int = 90
    face_scale_factor: float = 1.08
    face_min_neighbors: int = 8
    face_aspect_ratio_min: float = 0.75
    face_aspect_ratio_max: float = 1.35
    max_face_center_y_ratio: float = 0.85
    center_x_min_ratio: float = 0.30
    center_x_max_ratio: float = 0.70
    center_y_min_ratio: float = 0.20
    center_y_max_ratio: float = 0.75
    low_face_visibility_threshold: float = 0.70
    low_brightness_threshold: float = 60.0
    blurry_threshold: float = 15.0
    happy_score_threshold: float = 50.0
    enable_emotion_analysis: bool = True
    max_analyzed_frames: int | None = None


@dataclass(slots=True)
class HeadMovementAmount:
    """Average movement of the main face center across sampled frames."""

    score: float
    label: str


@dataclass(slots=True)
class VideoPresentationMetrics:
    """Observable presentation metrics from sampled video frames."""

    face_visible_ratio: float
    camera_facing_ratio: float
    candidate_centered_ratio: float
    head_movement_amount: HeadMovementAmount
    emotion_analysis_available: bool
    happy_frame_ratio: float | None
    happy_score_mean: float | None
    dominant_emotion_counts: dict[str, int]
    smile_frequency: float | None


@dataclass(slots=True)
class VideoQualityMetrics:
    """Basic video quality metrics from sampled video frames."""

    brightness_mean: float
    blur_score_mean: float
    resolution: str
    fps: float
    multiple_faces_detected: bool


@dataclass(slots=True)
class VideoAnalysisResult:
    """JSON-friendly summary returned by ``VideoAnalyzer``."""

    video_path: str
    frame_count: int
    fps: float
    width: int
    height: int
    resolution: str
    duration_sec: float
    sampled_frames: int
    video_presentation: VideoPresentationMetrics
    video_quality: VideoQualityMetrics
    face_detected: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass to a plain dictionary for JSON output."""
        return asdict(self)
