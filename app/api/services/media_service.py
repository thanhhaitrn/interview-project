"""Transcription + delivery analysis for recorded answers.

Factored out of the CLI ``run_transcribe_cli`` / ``_analyze_speech`` flow so
the web ``/api/transcribe`` endpoint and the CLI share one implementation.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def transcribe_and_analyze(
    media_path: str | Path,
    *,
    model_size: str = "small.en",
    language: str = "en",
    skip_analysis: bool = False,
) -> dict[str, Any]:
    """Transcribe an audio/video file and add fluency + voice metrics.

    The recording is decoded to a mono waveform once (PyAV reads the whole
    stream sequentially, which is reliable even for non-seekable browser WebM
    blobs) and re-encoded to a clean WAV before transcription. This avoids the
    truncated transcripts and failed voice analysis that happen when WebM with
    no duration header is fed straight into the transcriber.

    Returns a dict shaped like the transcript JSON the CLI writes, plus a
    compact ``delivery_metrics`` block ready to feed into answer evaluation.
    """
    from app.speech_analysis import (
        analyze_fluency,
        analyze_voice,
        build_delivery_metrics,
        decode_audio_mono,
        has_audio_stream,
        write_wav_mono,
    )
    from app.transcription import VideoTranscriber

    media_path = str(media_path)

    if not has_audio_stream(media_path):
        return {"text": "", "warnings": ["No audio stream found in the recording."]}

    # Decode the full audio once, then transcribe a clean WAV copy of it.
    samples, sample_rate = decode_audio_mono(media_path)

    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    try:
        write_wav_mono(samples, sample_rate, wav_path)
        transcriber = VideoTranscriber(model_size=model_size)
        # Self-contained answers: don't condition each window on the previous
        # text, which prevents the decoder from cutting off mid-recording.
        result = transcriber.transcribe(
            wav_path, language=language, condition_on_previous_text=False
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    payload: dict[str, Any] = result.to_dict()
    # Keep the original media path rather than the temp WAV path.
    payload["source_path"] = media_path

    if not skip_analysis:
        try:
            payload["fluency"] = analyze_fluency(result.all_words()).to_dict()
        except Exception as exc:  # noqa: BLE001 - fluency is best-effort
            payload["fluency"] = {"error": str(exc)}

        try:
            # Reuse the already-decoded PCM samples so voice analysis runs on
            # the same reliable audio that produced the transcript.
            payload["voice"] = analyze_voice(samples, sample_rate).to_dict()
        except Exception as exc:  # noqa: BLE001 - voice analysis is best-effort
            payload["voice"] = {"error": str(exc)}

        payload["delivery_metrics"] = build_delivery_metrics(payload)

    return payload
