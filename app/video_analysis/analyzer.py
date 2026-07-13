"""Simple video analyzer for local OpenCV experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import math
from pathlib import Path
from typing import Any

import cv2

from app.video_analysis.features import (
    box_center,
    calculate_blur_score,
    calculate_brightness,
    crop_box_region,
    detect_faces,
    filter_face_boxes,
    filter_significant_face_boxes,
    is_box_centered,
    load_haar_cascade,
    pick_tracked_face,
)
from app.video_analysis.schemas import (
    HeadMovementAmount,
    VideoAnalysisConfig,
    VideoAnalysisResult,
    VideoPresentationMetrics,
    VideoQualityMetrics,
)


class VideoAnalyzer:
    """Analyze basic quality and face visibility signals from a video file."""

    def __init__(self, config: VideoAnalysisConfig | None = None) -> None:
        self.config = config or VideoAnalysisConfig()
        self.face_cascade = load_haar_cascade("haarcascade_frontalface_default.xml")
        if self.face_cascade is None:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            raise RuntimeError(f"Failed to load Haar cascade at: {cascade_path}")

        self.deepface = self._load_deepface() if self.config.enable_emotion_analysis else None

    def _load_deepface(self) -> Any | None:
        """Import DeepFace only when emotion analysis is enabled."""
        try:
            from deepface import DeepFace
        except Exception:
            return None
        return DeepFace

    def _head_movement_label(self, score: float) -> str:
        if score < 0.04:
            return "low"
        if score < 0.12:
            return "moderate"
        return "high"

    def _deepface_emotion(self, frame: Any) -> tuple[str | None, float | None]:
        """Return dominant emotion and happy score from DeepFace, if possible."""
        if self.deepface is None:
            return None, None

        result = self.deepface.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
        )
        if isinstance(result, list):
            if not result:
                return None, None
            result = result[0]

        if not isinstance(result, dict):
            return None, None

        dominant_emotion = result.get("dominant_emotion")
        emotions = result.get("emotion") or {}
        happy_score = emotions.get("happy")
        if happy_score is None:
            return str(dominant_emotion) if dominant_emotion else None, None

        return (
            str(dominant_emotion) if dominant_emotion else None,
            float(happy_score),
        )

    def _runtime_config(
        self,
        sample_every_n: int | None,
        config: VideoAnalysisConfig | None,
    ) -> VideoAnalysisConfig:
        runtime_config = config or self.config
        if sample_every_n is not None:
            runtime_config = replace(runtime_config, sample_every_n=sample_every_n)
        if runtime_config.sample_every_n <= 0:
            raise ValueError("sample_every_n must be greater than 0.")
        if runtime_config.min_face_size <= 0:
            raise ValueError("min_face_size must be greater than 0.")
        return runtime_config

    def analyze(
        self,
        video_path: str,
        sample_every_n: int | None = None,
        config: VideoAnalysisConfig | None = None,
    ) -> VideoAnalysisResult:
        """Analyze a video and return a JSON-friendly summary object."""
        runtime_config = self._runtime_config(sample_every_n, config)

        path = Path(video_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ValueError(f"Could not open video file: {path}")

        warnings: list[str] = []
        if runtime_config.enable_emotion_analysis and self.deepface is None:
            self.deepface = self._load_deepface()

        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration_sec = float(frame_count / fps) if fps > 0 else 0.0
            resolution = f"{width}x{height}"

            sampled_frames = 0
            frames_with_face = 0
            camera_facing_frames = 0
            centered_frames = 0
            happy_frames = 0
            happy_scores: list[float] = []
            emotion_failures = 0
            dominant_emotions: Counter[str] = Counter()
            multiple_faces_detected = False
            brightness_total = 0.0
            blur_total = 0.0
            movement_total = 0.0
            movement_steps = 0
            previous_face_center: tuple[float, float] | None = None
            previous_main_face = None
            frame_diagonal = math.hypot(width, height) if width and height else 1.0

            emotion_requested = runtime_config.enable_emotion_analysis
            emotion_import_available = self.deepface is not None

            frame_index = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                if frame_index % runtime_config.sample_every_n == 0:
                    sampled_frames += 1

                    brightness = calculate_brightness(frame)
                    raw_faces = detect_faces(
                        frame,
                        self.face_cascade,
                        scale_factor=runtime_config.face_scale_factor,
                        min_neighbors=runtime_config.face_min_neighbors,
                        min_face_size=runtime_config.min_face_size,
                    )
                    valid_faces = filter_face_boxes(
                        raw_faces,
                        frame_height=height,
                        frame_width=width,
                        min_face_size=runtime_config.min_face_size,
                        aspect_ratio_min=runtime_config.face_aspect_ratio_min,
                        aspect_ratio_max=runtime_config.face_aspect_ratio_max,
                        max_center_y_ratio=runtime_config.max_face_center_y_ratio,
                    )
                    main_face = pick_tracked_face(valid_faces, previous_main_face)
                    significant_faces = filter_significant_face_boxes(
                        valid_faces,
                        main_face,
                    )
                    blur_frame = (
                        crop_box_region(frame, main_face)
                        if main_face is not None
                        else frame
                    )
                    blur_score = calculate_blur_score(blur_frame)

                    brightness_total += brightness
                    blur_total += blur_score
                    if len(significant_faces) > 1:
                        multiple_faces_detected = True

                    if main_face is not None:
                        frames_with_face += 1
                        previous_main_face = main_face
                        face_center = box_center(main_face)

                        if is_box_centered(
                            main_face,
                            width,
                            height,
                            x_min_ratio=runtime_config.center_x_min_ratio,
                            x_max_ratio=runtime_config.center_x_max_ratio,
                            y_min_ratio=runtime_config.center_y_min_ratio,
                            y_max_ratio=runtime_config.center_y_max_ratio,
                        ):
                            centered_frames += 1
                            # This accepts screen-facing or camera-facing posture; it is not gaze tracking.
                            camera_facing_frames += 1

                        if previous_face_center is not None:
                            movement_total += (
                                math.dist(previous_face_center, face_center)
                                / frame_diagonal
                            )
                            movement_steps += 1

                        previous_face_center = face_center

                        if emotion_requested and emotion_import_available:
                            try:
                                face_crop = crop_box_region(frame, main_face, margin_ratio=0.05)
                                dominant_emotion, happy_score = self._deepface_emotion(face_crop)
                            except Exception:
                                emotion_failures += 1
                            else:
                                if happy_score is None:
                                    emotion_failures += 1
                                else:
                                    happy_scores.append(happy_score)
                                    if dominant_emotion:
                                        dominant_emotions[dominant_emotion] += 1
                                    if (
                                        dominant_emotion == "happy"
                                        or happy_score >= runtime_config.happy_score_threshold
                                    ):
                                        happy_frames += 1

                    if (
                        runtime_config.max_analyzed_frames is not None
                        and sampled_frames >= runtime_config.max_analyzed_frames
                    ):
                        break

                frame_index += 1

            if sampled_frames == 0:
                brightness_mean = 0.0
                blur_score_mean = 0.0
                face_visible_ratio = 0.0
                camera_facing_ratio = 0.0
                candidate_centered_ratio = 0.0
                emotion_analysis_available = False
                happy_frame_ratio = None
                happy_score_mean = None
                warnings.append("no_frames_sampled")
            else:
                brightness_mean = brightness_total / sampled_frames
                blur_score_mean = blur_total / sampled_frames
                face_visible_ratio = frames_with_face / sampled_frames
                camera_facing_ratio = camera_facing_frames / sampled_frames
                candidate_centered_ratio = centered_frames / sampled_frames
                emotion_analysis_available = bool(happy_scores)
                happy_frame_ratio = (
                    happy_frames / len(happy_scores)
                    if emotion_analysis_available
                    else None
                )
                happy_score_mean = (
                    sum(happy_scores) / len(happy_scores)
                    if emotion_analysis_available
                    else None
                )

                if frames_with_face == 0:
                    warnings.append("no_face_detected")
                elif face_visible_ratio < runtime_config.low_face_visibility_threshold:
                    warnings.append("low_face_visibility")
                if brightness_mean < runtime_config.low_brightness_threshold:
                    warnings.append("low_brightness")
                if blur_score_mean < runtime_config.blurry_threshold:
                    warnings.append("blurry_video")
                if multiple_faces_detected:
                    warnings.append("multiple_faces_detected")

                if emotion_requested and not emotion_analysis_available:
                    warnings.append("emotion_analysis_unavailable")
                if emotion_analysis_available and (
                    emotion_failures > 0
                    or face_visible_ratio < runtime_config.low_face_visibility_threshold
                    or brightness_mean < runtime_config.low_brightness_threshold
                    or blur_score_mean < runtime_config.blurry_threshold
                ):
                    warnings.append("emotion_analysis_may_be_unreliable")

            smile_frequency = happy_frame_ratio

            warnings.append(
                "camera_facing_ratio_is_approximate_not_eye_contact"
            )

            movement_score = movement_total / movement_steps if movement_steps else 0.0

            return VideoAnalysisResult(
                video_path=str(path),
                frame_count=frame_count,
                fps=fps,
                width=width,
                height=height,
                resolution=resolution,
                duration_sec=duration_sec,
                sampled_frames=sampled_frames,
                video_presentation=VideoPresentationMetrics(
                    face_visible_ratio=face_visible_ratio,
                    camera_facing_ratio=camera_facing_ratio,
                    candidate_centered_ratio=candidate_centered_ratio,
                    head_movement_amount=HeadMovementAmount(
                        score=movement_score,
                        label=self._head_movement_label(movement_score),
                    ),
                    emotion_analysis_available=emotion_analysis_available,
                    happy_frame_ratio=happy_frame_ratio,
                    happy_score_mean=happy_score_mean,
                    dominant_emotion_counts=dict(dominant_emotions),
                    smile_frequency=smile_frequency,
                ),
                video_quality=VideoQualityMetrics(
                    brightness_mean=brightness_mean,
                    blur_score_mean=blur_score_mean,
                    resolution=resolution,
                    fps=fps,
                    multiple_faces_detected=multiple_faces_detected,
                ),
                face_detected=frames_with_face > 0,
                warnings=warnings,
            )
        finally:
            capture.release()
