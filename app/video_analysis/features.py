"""Frame-level OpenCV feature helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import cv2

Box = tuple[int, int, int, int]


def calculate_brightness(frame: Any) -> float:
    """Return mean grayscale intensity for a frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def calculate_blur_score(frame: Any) -> float:
    """Return blur score using variance of Laplacian."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def crop_box_region(frame: Any, box: Box, margin_ratio: float = 0.15) -> Any:
    """Crop a box with a small margin, staying inside frame bounds."""
    x, y, w, h = box
    frame_height, frame_width = frame.shape[:2]
    margin_x = int(w * margin_ratio)
    margin_y = int(h * margin_ratio)

    x1 = max(x - margin_x, 0)
    y1 = max(y - margin_y, 0)
    x2 = min(x + w + margin_x, frame_width)
    y2 = min(y + h + margin_y, frame_height)

    return frame[y1:y2, x1:x2]


def load_haar_cascade(file_name: str) -> cv2.CascadeClassifier | None:
    """Load one OpenCV Haar cascade by file name."""
    cascade_path = Path(cv2.data.haarcascades) / file_name
    cascade = cv2.CascadeClassifier(str(cascade_path))
    return None if cascade.empty() else cascade


def to_box_list(raw_boxes: Iterable[Iterable[int]]) -> list[Box]:
    """Convert OpenCV boxes into plain integer tuples."""
    return [
        (int(x), int(y), int(w), int(h))
        for x, y, w, h in raw_boxes
    ]


def detect_faces(
    frame: Any,
    face_cascade: Any,
    *,
    scale_factor: float = 1.08,
    min_neighbors: int = 8,
    min_face_size: int = 90,
) -> list[Box]:
    """Detect faces in one frame using Haar cascades."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=scale_factor,
        minNeighbors=min_neighbors,
        minSize=(min_face_size, min_face_size),
    )
    return to_box_list(faces)


def filter_face_boxes(
    boxes: list[Box],
    frame_height: int,
    frame_width: int | None = None,
    min_face_size: int = 90,
    aspect_ratio_min: float = 0.75,
    aspect_ratio_max: float = 1.35,
    max_center_y_ratio: float = 0.85,
) -> list[Box]:
    """Remove common false-positive face boxes."""
    valid: list[Box] = []
    dynamic_min_size = min_face_size
    if frame_width is not None:
        dynamic_min_size = max(min_face_size, int(min(frame_width, frame_height) * 0.12))

    for x, y, w, h in boxes:
        if w < dynamic_min_size or h < dynamic_min_size:
            continue

        aspect_ratio = float(w) / float(h) if h > 0 else 0.0
        if aspect_ratio < aspect_ratio_min or aspect_ratio > aspect_ratio_max:
            continue

        center_y = y + (h / 2.0)
        if center_y > frame_height * max_center_y_ratio:
            continue

        valid.append((x, y, w, h))

    return valid


def filter_significant_face_boxes(
    boxes: list[Box],
    main_box: Box | None,
    min_area_ratio: float = 0.45,
) -> list[Box]:
    """Keep boxes large enough to plausibly be another nearby face."""
    if main_box is None:
        return []

    main_area = main_box[2] * main_box[3]
    if main_area <= 0:
        return []

    return [
        box
        for box in boxes
        if (box[2] * box[3]) >= main_area * min_area_ratio
    ]


def pick_largest_box(boxes: list[Box]) -> Box | None:
    """Return the largest face box by area."""
    if not boxes:
        return None
    return max(boxes, key=lambda box: box[2] * box[3])


def box_center(box: Box) -> tuple[float, float]:
    """Return center x/y for a bounding box."""
    x, y, w, h = box
    return x + (w / 2.0), y + (h / 2.0)


def pick_tracked_face(
    boxes: list[Box],
    previous_box: Box | None,
) -> Box | None:
    """Prefer the face nearest to the previous main face; fall back to largest."""
    if not boxes:
        return None
    if previous_box is None:
        return pick_largest_box(boxes)

    previous_center = box_center(previous_box)
    return min(
        boxes,
        key=lambda box: (
            abs(box_center(box)[0] - previous_center[0])
            + abs(box_center(box)[1] - previous_center[1])
        ),
    )


def is_box_centered(
    box: Box,
    frame_width: int,
    frame_height: int,
    *,
    x_min_ratio: float = 0.30,
    x_max_ratio: float = 0.70,
    y_min_ratio: float = 0.20,
    y_max_ratio: float = 0.75,
) -> bool:
    """Check whether the main face center is in the central frame region."""
    center_x, center_y = box_center(box)
    return (
        frame_width * x_min_ratio <= center_x <= frame_width * x_max_ratio
        and frame_height * y_min_ratio <= center_y <= frame_height * y_max_ratio
    )
