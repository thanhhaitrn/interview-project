"""Record local audio/video answers for the existing file-based pipelines."""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class RecordingError(RuntimeError):
    """User-facing recording error that can fall back to typed text."""


def _recording_path(output_dir: Path, prefix: str, suffix: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{prefix}_{timestamp}{suffix}"


def _validate_output_file(path: Path, media_label: str) -> None:
    if not path.exists():
        raise RecordingError(f"Recorded {media_label} was not created: {path}")
    if path.stat().st_size <= 0:
        raise RecordingError(f"Recorded {media_label} is empty: {path}")


def _friendly_import_error(package_name: str) -> RecordingError:
    return RecordingError(
        f"Missing recording dependency: {package_name}. "
        "Install recording dependencies with:\n"
        "./.venv/bin/python -m pip install -r requirements.txt"
    )


def record_audio_answer(
    output_dir: Path,
    duration_seconds: int,
    sample_rate: int = 16000,
) -> Path:
    """Record microphone audio to a WAV file and return the saved path."""
    if duration_seconds <= 0:
        raise RecordingError("Recording duration must be greater than 0 seconds.")
    if sample_rate <= 0:
        raise RecordingError("Recording sample rate must be greater than 0.")

    try:
        import sounddevice as sd
    except ModuleNotFoundError as exc:
        raise _friendly_import_error("sounddevice") from exc

    try:
        import soundfile as sf
    except ModuleNotFoundError as exc:
        raise _friendly_import_error("soundfile") from exc

    output_path = _recording_path(output_dir, "recorded_audio", ".wav")
    print(f"[RECORD] Recording microphone for {duration_seconds} seconds...")

    try:
        recording: Any = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
    except Exception as exc:  # noqa: BLE001 - hardware errors are user-facing.
        raise RecordingError(
            "Could not record microphone audio. Check microphone permission, "
            "input device availability, or close other apps using the microphone."
        ) from exc

    try:
        import numpy as np

        rms = float(np.sqrt(np.mean(np.square(recording)))) if recording.size else 0.0
    except Exception:
        rms = 0.0

    if rms < 0.00001:
        raise RecordingError(
            "Recorded audio is too quiet or empty. Check microphone permission "
            "and input volume."
        )

    try:
        sf.write(str(output_path), recording, sample_rate)
    except Exception as exc:  # noqa: BLE001 - file/codec errors are user-facing.
        raise RecordingError(f"Could not save recorded audio to {output_path}.") from exc

    _validate_output_file(output_path, "audio")
    return output_path


def _ffmpeg_binary() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RecordingError(
            "ffmpeg was not found. Record video mode requires the ffmpeg CLI "
            "so webcam video and microphone audio are captured together. "
            "Install ffmpeg, or use video file mode."
        )
    return ffmpeg_path


def _avfoundation_input(camera_device: str | None, audio_device: str | None) -> str:
    camera = camera_device or "0"
    audio = audio_device or "0"
    return f"{camera}:{audio}"


def record_video_answer(
    output_dir: Path,
    duration_seconds: int,
    camera_device: str | None = None,
    audio_device: str | None = None,
) -> Path:
    """Record webcam video with microphone audio to an MP4 file."""
    if duration_seconds <= 0:
        raise RecordingError("Recording duration must be greater than 0 seconds.")

    if platform.system() != "Darwin":
        raise RecordingError(
            "Record video mode currently supports macOS ffmpeg avfoundation only. "
            "Use video file mode on this platform."
        )

    output_path = _recording_path(output_dir, "recorded_video", ".mp4")
    ffmpeg_path = _ffmpeg_binary()
    ffmpeg_input = _avfoundation_input(camera_device, audio_device)

    print(f"[RECORD] Recording webcam + microphone for {duration_seconds} seconds...")
    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "avfoundation",
        "-framerate",
        "30",
        "-i",
        ffmpeg_input,
        "-t",
        str(duration_seconds),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RecordingError(
            "Could not start ffmpeg for video recording. Check that ffmpeg is installed."
        ) from exc

    if completed.returncode != 0:
        stderr_tail = "\n".join(completed.stderr.splitlines()[-8:])
        raise RecordingError(
            "ffmpeg could not record webcam + microphone. Check camera/microphone "
            "permission, device names, or close other apps using the devices."
            f"\nffmpeg output:\n{stderr_tail}"
        )

    _validate_output_file(output_path, "video")
    validate_recorded_video_has_audio(output_path)
    return output_path


def validate_recorded_video_has_audio(video_path: Path) -> None:
    """Reject recorded videos that do not contain a decodable audio stream."""
    try:
        from app.speech_analysis import has_audio_stream
    except (ImportError, ModuleNotFoundError) as exc:
        raise RecordingError(
            "Could not validate recorded video audio because PyAV/faster-whisper "
            "dependencies are missing. Install requirements, then try again."
        ) from exc

    try:
        has_audio = has_audio_stream(str(video_path))
    except Exception as exc:  # noqa: BLE001 - invalid media should be user-facing.
        raise RecordingError(
            f"Could not inspect the recorded video audio stream: {video_path}"
        ) from exc

    if not has_audio:
        raise RecordingError(
            "Recorded video has no audio stream. Record video mode requires "
            "microphone audio so transcription and speech analysis can run."
        )
