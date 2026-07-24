"""Transcription + delivery analysis for recorded answers.

Factored out of the CLI ``run_transcribe_cli`` / ``_analyze_speech`` flow so
the web ``/api/transcribe`` endpoint and the CLI share one implementation.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

# Cap sampled frames so DeepFace emotion analysis stays fast enough for a web
# request; quality/visibility ratios remain stable with this many samples.
_WEB_MAX_ANALYZED_FRAMES = 40


def analyze_video_presentation(media_path: str | Path) -> dict[str, Any] | None:
    """Run face/presentation analysis on a video answer, best-effort.

    Returns the ``video_presentation`` section of ``VideoAnalysisResult`` (the
    same payload the CLI's ``--with-video`` evaluation uses), or ``None`` when
    the analysis is unavailable or fails.
    """
    from app.video_analysis import VideoAnalysisConfig, VideoAnalyzer

    try:
        config = VideoAnalysisConfig(max_analyzed_frames=_WEB_MAX_ANALYZED_FRAMES)
        result = VideoAnalyzer(config).analyze(video_path=str(media_path))
        return result.to_dict().get("video_presentation")
    except Exception:  # noqa: BLE001 - face metrics are optional
        return None


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
        has_video_stream,
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

        video_metrics = None
        try:
            if has_video_stream(media_path):
                video_metrics = analyze_video_presentation(media_path)
        except Exception:  # noqa: BLE001 - video probing is best-effort
            video_metrics = None
        if video_metrics:
            payload["video_presentation"] = video_metrics

        payload["delivery_metrics"] = build_delivery_metrics(payload, video_metrics)

    return payload
