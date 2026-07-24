"""Media endpoints: transcribe + analyze a recorded audio/video answer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api import deps
from app.api.schemas_api import TranscribeResponse
from app.api.services import media_service

router = APIRouter(prefix="/api", tags=["media"])

_SUFFIX_BY_TYPE = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "video/mp4": ".mp4",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def _suffix_for(file: UploadFile) -> str:
    if file.content_type in _SUFFIX_BY_TYPE:
        return _SUFFIX_BY_TYPE[file.content_type]
    name = (file.filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ".webm"


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    model_size: str = Form("small.en"),
    language: str = Form("en"),
) -> TranscribeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded recording is empty.")

    # Persist the recording like the CLI answer modes do, so it can be
    # reviewed or re-analyzed later (data/uploads/ is git-ignored).
    deps.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    media_path: Path = deps.UPLOADS_DIR / f"answer_{timestamp}{_suffix_for(file)}"
    media_path.write_bytes(data)

    try:
        result: dict[str, Any] = media_service.transcribe_and_analyze(
            media_path, model_size=model_size, language=language
        )
    except Exception as exc:  # noqa: BLE001 - surface decode/transcribe errors
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

    return TranscribeResponse(
        text=result.get("text", ""),
        fluency=result.get("fluency"),
        voice=result.get("voice"),
        video_presentation=result.get("video_presentation"),
        delivery_metrics=result.get("delivery_metrics"),
        recording_path=str(media_path),
    )
