"""Media endpoints: transcribe a recorded audio/video answer."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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

    suffix = _suffix_for(file)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        result: dict[str, Any] = media_service.transcribe_and_analyze(
            tmp_path, model_size=model_size, language=language
        )
    except Exception as exc:  # noqa: BLE001 - surface decode/transcribe errors
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    return TranscribeResponse(
        text=result.get("text", ""),
        fluency=result.get("fluency"),
        voice=result.get("voice"),
        delivery_metrics=result.get("delivery_metrics"),
    )
