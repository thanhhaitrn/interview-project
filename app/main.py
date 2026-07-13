"""App CLI for resume preparation, workflow inspection, and interviews."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from app.agent import llm_client
from app.agent.outputs import clean_empty_fields
from app.graph.workflow import workflow_steps
from app.graph.workflow import resume_interview, start_interview
from app.resume_system.parser import PARSED_DIR, RAW_DIR, parse_pdf_to_json
from app.resume_system.resume_normalizer import LLM_DIR, save_llm_resume


DATA_DIR = Path("data")
JOBS_DIR = DATA_DIR / "jobs"
INTERVIEW_RUNS_DIR = DATA_DIR / "interview_runs"
VIDEO_DIR = DATA_DIR / "video"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
ANSWER_EVALS_DIR = DATA_DIR / "answer_evaluations"
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MEDIA_SUFFIXES = AUDIO_SUFFIXES | VIDEO_SUFFIXES


def build_mermaid_workflow() -> str:
    """Generate Mermaid text from the interview graph workflow steps."""
    lines = ["flowchart TD"]

    for index, step in enumerate(workflow_steps()):
        lines.append(f'  N{index}["{step}"]')
        if index > 0:
            lines.append(f"  N{index - 1} --> N{index}")

    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)

    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    try:
        json.dumps(value)
    except TypeError:
        return str(value)

    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    payload = clean_empty_fields(_jsonable(payload))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _interview_run_name(started_at: datetime, thread_id: str) -> str:
    return f"{started_at.strftime('%Y%m%d_%H%M%S')}_{thread_id[:8]}"


def _list_files(folder: Path, suffixes: set[str]) -> list[Path]:
    if not folder.exists():
        return []

    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _select_path(
    *,
    label: str,
    provided_path: Path | None,
    folder: Path,
    suffixes: set[str],
) -> Path:
    if provided_path is not None:
        if not provided_path.exists():
            raise SystemExit(f"{label} file does not exist: {provided_path}")
        if provided_path.suffix.lower() not in suffixes:
            supported = ", ".join(sorted(suffixes))
            raise SystemExit(f"{label} file must use one of: {supported}")
        return provided_path

    files = _list_files(folder, suffixes)
    if not files:
        supported = ", ".join(sorted(suffixes))
        raise SystemExit(f"No {label} files found in {folder} ({supported}).")

    print(f"\nSelect {label}:")
    for index, path in enumerate(files, start=1):
        print(f"  {index}. {path}")

    if not sys.stdin.isatty():
        print(f"Using default {label}: {files[0]}")
        return files[0]

    while True:
        raw_choice = input(f"Choose number [1-{len(files)}] (default 1): ").strip()
        if not raw_choice:
            return files[0]

        if raw_choice.isdigit():
            choice = int(raw_choice)
            if 1 <= choice <= len(files):
                return files[choice - 1]

        print("Invalid choice. Please enter one of the listed numbers.")


def _validate_existing_media_path(
    path: Path,
    *,
    label: str,
    suffixes: set[str],
) -> Path:
    if not path.exists():
        raise ValueError(f"{label} file does not exist: {path}")
    if path.suffix.lower() not in suffixes:
        supported = ", ".join(sorted(suffixes))
        raise ValueError(f"{label} file must use one of: {supported}")
    return path


def _prompt_for_media_path(*, label: str, suffixes: set[str]) -> Path:
    supported = ", ".join(sorted(suffixes))
    while True:
        raw_path = input(f"Enter {label} file path ({supported}): ").strip()
        if raw_path.lower() in {"exit", "quit", ":q"}:
            raise KeyboardInterrupt
        if not raw_path:
            print("Please enter a file path, or type 'exit' to stop.")
            continue

        try:
            return _validate_existing_media_path(
                Path(raw_path).expanduser(),
                label=label,
                suffixes=suffixes,
            )
        except ValueError as exc:
            print(f"[ANSWER MODE] {exc}")


def _choose_answer_mode(configured_mode: str) -> str:
    if configured_mode != "ask":
        return configured_mode.replace("-", "_")

    if not sys.stdin.isatty():
        return "text"

    print("\nChoose answer mode:")
    print("  1. Text")
    print("  2. Audio file")
    print("  3. Video file")
    print("  4. Record audio")
    print("  5. Record video")

    choices = {
        "1": "text",
        "text": "text",
        "t": "text",
        "2": "audio",
        "audio": "audio",
        "audio file": "audio",
        "a": "audio",
        "3": "video",
        "video": "video",
        "video file": "video",
        "v": "video",
        "4": "record_audio",
        "record audio": "record_audio",
        "record-audio": "record_audio",
        "record_audio": "record_audio",
        "ra": "record_audio",
        "5": "record_video",
        "record video": "record_video",
        "record-video": "record_video",
        "record_video": "record_video",
        "rv": "record_video",
    }

    while True:
        raw_choice = input("Choose 1, 2, 3, 4, or 5: ").strip().lower()
        if not raw_choice:
            print(
                "Please choose 1 for text, 2 for audio, 3 for video, "
                "4 for record audio, or 5 for record video."
            )
            continue
        mode = choices.get(raw_choice)
        if mode:
            return mode
        print(
            "Invalid choice. Please choose 1 for text, 2 for audio, "
            "3 for video, 4 for record audio, or 5 for record video."
        )


def _prompt_recording_duration(default_seconds: int) -> int:
    if not sys.stdin.isatty():
        return default_seconds

    while True:
        raw_duration = input(
            f"Enter recording duration in seconds [{default_seconds}]: "
        ).strip()
        if not raw_duration:
            return default_seconds
        if raw_duration.lower() in {"cancel", "exit", "quit", ":q"}:
            raise RuntimeError("Recording cancelled.")
        if raw_duration.isdigit() and int(raw_duration) > 0:
            return int(raw_duration)
        print("Please enter a positive whole number of seconds, or press Enter.")


def _media_dependency_help(exc: Exception) -> str:
    message = str(exc)
    missing_name = getattr(exc, "name", "")
    if isinstance(exc, ModuleNotFoundError) and missing_name:
        message = f"Missing Python module: {missing_name}"

    return (
        f"{message}\n"
        "Install the media dependencies, then try again:\n"
        "./.venv/bin/python -m pip install -r requirements.txt"
    )


def _transcribe_media_answer(
    media_path: Path,
    *,
    model: str,
    language: str,
) -> tuple[str, dict[str, Any]]:
    from app.speech_analysis import build_delivery_metrics, has_audio_stream
    from app.transcription import VideoTranscriber

    try:
        has_audio = has_audio_stream(str(media_path))
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(_media_dependency_help(exc)) from exc

    if not has_audio:
        raise RuntimeError(f"No audio track found in {media_path}.")

    print(f"[ANSWER MODE] Transcribing {media_path} with model '{model}' ...")
    try:
        transcriber = VideoTranscriber(model_size=model)
        result = transcriber.transcribe(str(media_path), language=language)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(_media_dependency_help(exc)) from exc

    transcript_payload = result.to_dict()
    transcript_payload.update(_analyze_speech(result, media_path))
    answer_text = result.text.strip()
    if not answer_text:
        raise RuntimeError("Transcription completed, but no answer text was detected.")

    return answer_text, build_delivery_metrics(transcript_payload)


def _compact_video_metrics(video_result: dict[str, Any]) -> dict[str, Any]:
    video_metrics: dict[str, Any] = {}

    presentation = video_result.get("video_presentation")
    if isinstance(presentation, dict):
        video_metrics["face"] = {
            key: presentation[key]
            for key in (
                "face_visible_ratio",
                "camera_facing_ratio",
                "candidate_centered_ratio",
                "head_movement_amount",
                "happy_frame_ratio",
                "happy_score_mean",
                "smile_frequency",
                "emotion_analysis_available",
            )
            if presentation.get(key) is not None
        }

    quality = video_result.get("video_quality")
    if isinstance(quality, dict):
        video_metrics["video_quality"] = {
            key: quality[key]
            for key in (
                "brightness_mean",
                "blur_score_mean",
                "resolution",
                "fps",
                "multiple_faces_detected",
            )
            if quality.get(key) is not None
        }

    warnings = video_result.get("warnings")
    if isinstance(warnings, list) and warnings:
        video_metrics["warnings"] = warnings

    return clean_empty_fields(video_metrics)


def _format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _video_warning_note(warning: str) -> str:
    notes = {
        "no_frames_sampled": "No frames could be sampled from this video.",
        "no_face_detected": "No face was detected in sampled frames.",
        "low_face_visibility": "Face was not visible in enough sampled frames.",
        "low_brightness": "Low light may affect presentation quality.",
        "blurry_video": "Blur may affect video presentation quality.",
        "multiple_faces_detected": "Multiple faces appeared in sampled frames.",
        "emotion_analysis_unavailable": "Emotion/happy analysis was unavailable.",
        "emotion_analysis_may_be_unreliable": "Emotion/happy analysis may be unreliable for this video.",
        "camera_facing_ratio_is_approximate_not_eye_contact": (
            "Camera-facing ratio is approximate and does not measure real eye contact."
        ),
    }
    return notes.get(warning, warning.replace("_", " ").capitalize() + ".")


def _print_video_feedback(video_result: dict[str, Any]) -> None:
    """Print compact, observable video feedback for interview practice."""
    presentation = video_result.get("video_presentation")
    if not isinstance(presentation, dict):
        presentation = {}

    quality = video_result.get("video_quality")
    if not isinstance(quality, dict):
        quality = {}

    warnings = video_result.get("warnings")
    warning_values = [str(item) for item in warnings] if isinstance(warnings, list) else []
    warning_set = set(warning_values)
    head_movement = presentation.get("head_movement_amount")
    if not isinstance(head_movement, dict):
        head_movement = {}

    brightness_status = "low" if "low_brightness" in warning_set else "ok"
    blur_status = "blurry" if "blurry_video" in warning_set else "ok"
    multiple_faces = "yes" if quality.get("multiple_faces_detected") else "no"
    camera_available = (
        "yes" if presentation.get("camera_facing_ratio") is not None else "no"
    )

    print(
        "[VIDEO] "
        f"face visible {_format_percent(presentation.get('face_visible_ratio'))} | "
        f"centered {_format_percent(presentation.get('candidate_centered_ratio'))} | "
        f"brightness {brightness_status} | "
        f"blur {blur_status} | "
        f"head movement {head_movement.get('label', 'n/a')} | "
        f"multiple faces {multiple_faces}"
    )
    print(
        "[VIDEO] "
        f"emotion/happy {_format_percent(presentation.get('happy_frame_ratio'))} | "
        f"camera-facing available: {camera_available}"
    )

    centered_ratio = presentation.get("candidate_centered_ratio")
    if isinstance(centered_ratio, (int, float)) and centered_ratio < 0.70:
        print("[VIDEO] note: Candidate was off-center in many sampled frames.")

    happy_ratio = presentation.get("happy_frame_ratio")
    if isinstance(happy_ratio, (int, float)) and happy_ratio < 0.05:
        print(
            "[VIDEO] note: Happy-expression signal was low; treat this as optional presentation context only."
        )

    if head_movement.get("label") == "high":
        print("[VIDEO] note: Head movement was high across sampled frames.")

    for warning in warning_values:
        if warning == "camera_facing_ratio_is_approximate_not_eye_contact":
            continue
        print(f"[VIDEO] note: {_video_warning_note(warning)}")


def process_audio_answer(
    audio_path: Path,
    *,
    model: str,
    language: str,
) -> tuple[str, dict[str, Any]]:
    """Transcribe an audio/video file and build speech delivery metrics."""
    return _transcribe_media_answer(
        audio_path,
        model=model,
        language=language,
    )


def process_video_answer(
    video_path: Path,
    *,
    model: str,
    language: str,
    sample_every_n: int,
) -> tuple[str, dict[str, Any]]:
    """Analyze video, then transcribe its audio for the answer text."""
    from app.video_analysis import VideoAnalysisConfig, VideoAnalyzer

    print(f"[ANSWER MODE] Analyzing video presentation metrics from {video_path} ...")
    video_result = VideoAnalyzer(
        VideoAnalysisConfig(sample_every_n=sample_every_n)
    ).analyze(str(video_path))
    video_result_payload = video_result.to_dict()
    _print_video_feedback(video_result_payload)

    answer_text, delivery_metrics = _transcribe_media_answer(
        video_path,
        model=model,
        language=language,
    )
    delivery_metrics.update(_compact_video_metrics(video_result_payload))
    return answer_text, clean_empty_fields(delivery_metrics)


def _collect_text_answer() -> str:
    answer = ""
    while not answer:
        answer = input("\n[USER ANSWER] ").strip()
        if answer.lower() in {"exit", "quit", ":q"}:
            raise KeyboardInterrupt
        if not answer:
            print("Please enter an answer, or type 'exit' to stop.")
    return answer


def _delete_recording_if_temporary(path: Path, *, keep_recordings: bool) -> None:
    if keep_recordings:
        return

    try:
        path.unlink(missing_ok=True)
        print(f"[RECORD] Deleted temporary recording {path}")
    except OSError as exc:
        print(f"[RECORD] Warning: could not delete temporary recording: {exc}")


def _collect_answer_payload(
    args: argparse.Namespace,
    *,
    recordings_dir: Path,
) -> dict[str, Any]:
    """Collect one answer in text/audio/video mode for the existing graph."""
    mode = _choose_answer_mode(args.answer_mode)

    if mode == "text":
        return {
            "answer": _collect_text_answer(),
            "answer_source": "text",
        }

    if mode == "audio":
        audio_path = _prompt_for_media_path(
            label="audio",
            suffixes=MEDIA_SUFFIXES,
        )
        answer_text, delivery_metrics = process_audio_answer(
            audio_path,
            model=args.transcription_model,
            language=args.transcription_language,
        )
        print(f"[ANSWER MODE] Transcript: {answer_text}")
        return {
            "answer": answer_text,
            "answer_source": "audio_file",
            "delivery_metrics": delivery_metrics,
        }

    if mode == "video":
        video_path = _prompt_for_media_path(
            label="video",
            suffixes=VIDEO_SUFFIXES,
        )
        answer_text, delivery_metrics = process_video_answer(
            video_path,
            model=args.transcription_model,
            language=args.transcription_language,
            sample_every_n=args.video_sample_every_n,
        )
        print(f"[ANSWER MODE] Transcript: {answer_text}")
        return {
            "answer": answer_text,
            "answer_source": "video_file",
            "delivery_metrics": delivery_metrics,
        }

    if mode == "record_audio":
        from app.media_recording import record_audio_answer

        duration = _prompt_recording_duration(args.record_seconds)
        recording_path = record_audio_answer(
            output_dir=recordings_dir,
            duration_seconds=duration,
            sample_rate=args.record_sample_rate,
        )
        print(f"[RECORD] Saved audio to {recording_path}")
        try:
            answer_text, delivery_metrics = process_audio_answer(
                recording_path,
                model=args.transcription_model,
                language=args.transcription_language,
            )
        finally:
            _delete_recording_if_temporary(
                recording_path,
                keep_recordings=args.keep_recordings,
            )
        print(f"[ANSWER MODE] Transcript: {answer_text}")
        return {
            "answer": answer_text,
            "answer_source": "record_audio",
            "delivery_metrics": delivery_metrics,
        }

    if mode == "record_video":
        from app.media_recording import record_video_answer

        duration = _prompt_recording_duration(args.record_seconds)
        recording_path = record_video_answer(
            output_dir=recordings_dir,
            duration_seconds=duration,
            camera_device=args.camera_device,
            audio_device=args.audio_device,
        )
        print(f"[RECORD] Saved video to {recording_path}")
        try:
            answer_text, delivery_metrics = process_video_answer(
                recording_path,
                model=args.transcription_model,
                language=args.transcription_language,
                sample_every_n=args.video_sample_every_n,
            )
        finally:
            _delete_recording_if_temporary(
                recording_path,
                keep_recordings=args.keep_recordings,
            )
        print(f"[ANSWER MODE] Transcript: {answer_text}")
        return {
            "answer": answer_text,
            "answer_source": "record_video",
            "delivery_metrics": delivery_metrics,
        }

    raise ValueError(f"Unsupported answer mode: {mode}")


def _load_job_payload(path: Path) -> dict[str, Any]:
    return {"job_description_context": [path.read_text(encoding="utf-8").strip()]}


def _build_interview_request(
    *,
    resume_path: Path,
    job_path: Path,
    interview_type: str,
    difficulty: str | None,
    question_count: int | None,
    max_followups_per_question: int,
) -> dict[str, Any]:
    interview_config: dict[str, Any] = {}
    if difficulty is not None:
        interview_config["difficulty_level"] = difficulty

    if question_count is not None:
        interview_config["question_count"] = question_count

    payload: dict[str, Any] = {
        "resume": _read_json(resume_path),
        "interview_type": interview_type,
        "interview_config": interview_config,
        "max_followups_per_question": max(0, max_followups_per_question),
    }
    if difficulty is not None:
        payload["difficulty"] = difficulty

    payload.update(_load_job_payload(job_path))
    return payload


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return clean_empty_fields(value.model_dump(exclude_none=True))

    if isinstance(value, dict):
        return clean_empty_fields(dict(value))

    return {}


def _extract_interrupt_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = state.get("__interrupt__")
    if not interrupts:
        return None

    if isinstance(interrupts, (list, tuple)):
        interrupt = interrupts[0]
    else:
        interrupt = interrupts

    value = getattr(interrupt, "value", interrupt)
    if isinstance(value, dict):
        return value

    return {"value": value}


def _question_text(question: dict[str, Any]) -> str:
    return str(question.get("question") or "").strip()


def _print_interview_plan(state: dict[str, Any]) -> None:
    questions = state.get("planned_questions") or []
    print(f"\n[PLAN] Generated {len(questions)} planned question(s).")

    for question in questions:
        question_id = question.get("id") or "q?"
        competency = question.get("competency") or "general"
        text = _question_text(question)
        print(f"- {question_id} [{competency}]: {text}")


def _format_score(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return str(score or "n/a")

    if value.is_integer():
        return str(int(value))

    return f"{value:.1f}"


def _feedback_text(evaluation: dict[str, Any]) -> str:
    if evaluation.get("summary"):
        return str(evaluation["summary"])

    coaching = evaluation.get("candidate_coaching")
    if isinstance(coaching, dict) and coaching.get("better_answer_strategy"):
        return str(coaching["better_answer_strategy"])

    weaknesses = evaluation.get("weaknesses") or []
    strengths = evaluation.get("strengths") or []
    parts = []
    if strengths:
        parts.append(f"Strengths: {', '.join(map(str, strengths[:2]))}")
    if weaknesses:
        parts.append(f"Needs work: {', '.join(map(str, weaknesses[:2]))}")

    return "; ".join(parts) if parts else "No detailed feedback returned."


def _decision_action(state: dict[str, Any], decision: dict[str, Any]) -> str:
    routed_action = state.get("next_node")
    if routed_action:
        return str(routed_action)

    turn = (state.get("turns") or [{}])[-1]
    if isinstance(turn, dict) and turn.get("routed_action"):
        return str(turn["routed_action"])

    return str(decision.get("action") or "final_report")


def _decision_label(action: str) -> str:
    labels = {
        "follow_up": "Ask follow-up",
        "next_question": "Ask next question",
        "final_report": "Create final report",
    }
    return labels.get(action, action)


def _latest_decision_reason(state: dict[str, Any], decision: dict[str, Any]) -> str:
    if decision.get("reason"):
        return str(decision["reason"])

    for key in ("turn_summaries", "turns"):
        turns = state.get(key) or []
        if not turns:
            continue

        latest_turn = turns[-1]
        if not isinstance(latest_turn, dict):
            continue

        if latest_turn.get("decision_reason"):
            return str(latest_turn["decision_reason"])

        turn_decision = latest_turn.get("decision")
        if isinstance(turn_decision, dict) and turn_decision.get("reason"):
            return str(turn_decision["reason"])

    return "No reason returned."


def _print_latest_turn_result(state: dict[str, Any]) -> None:
    evaluation = _model_dump(state.get("latest_evaluation"))
    if evaluation:
        print(
            "\n[EVALUATION] "
            f"Score: {_format_score(evaluation.get('overall_score'))}/5"
        )
        print(f"[FEEDBACK] {_feedback_text(evaluation)}")

    decision = _model_dump(state.get("latest_decision"))
    if decision or state.get("next_node"):
        action = _decision_action(state, decision)
        print("\n[STATE] Current stage: decide_next_step")
        print(f"[DECISION] {_decision_label(action)}")
        print(f"[REASON] {_latest_decision_reason(state, decision)}")


def _token_summary(llm_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prompt_tokens": sum(
            int(
                call.get("prompt_tokens")
                or call.get("prompt_tokens_estimate")
                or 0
            )
            for call in llm_calls
        ),
        "completion_tokens": sum(
            int(
                call.get("completion_tokens")
                or call.get("completion_tokens_estimate")
                or 0
            )
            for call in llm_calls
        ),
        "total_tokens": sum(
            int(call.get("total_tokens") or call.get("total_tokens_estimate") or 0)
            for call in llm_calls
        ),
        "token_source": (
            "provider_usage_metadata"
            if any(
                call.get("token_source") == "provider_usage_metadata"
                for call in llm_calls
            )
            else "estimated_chars_div_4"
        ),
    }


def _render_report_markdown(report_payload: dict[str, Any]) -> str:
    metadata = report_payload["metadata"]
    report = report_payload.get("final_report") or {}
    turns = report_payload.get("turn_summaries") or report_payload.get("turns") or []
    token_summary = metadata["tokens"]

    lines = [
        "# Interview Report",
        "",
        f"- Status: {metadata['status']}",
        f"- Resume: {metadata['resume_path']}",
        f"- Job description: {metadata['job_path']}",
        f"- Runtime seconds: {metadata['runtime_seconds']}",
        f"- Tokens: {token_summary['total_tokens']}",
        f"- Token source: {token_summary['token_source']}",
        "",
    ]

    if report:
        lines.extend(
            [
                "## Final Summary",
                "",
                f"- Recommendation: {report.get('overall_recommendation', '')}",
                f"- Summary: {report.get('summary', '')}",
                "",
            ]
        )

        for title, key in (
            ("Strengths", "strengths"),
            ("Risks", "risks"),
            ("Evidence Highlights", "evidence_highlights"),
            ("Suggested Next Steps", "suggested_next_steps"),
        ):
            values = report.get(key) or []
            if values:
                lines.extend([f"## {title}", ""])
                lines.extend(f"- {value}" for value in values)
                lines.append("")

    if turns:
        lines.extend(["## Turns", ""])
        for index, turn in enumerate(turns, start=1):
            question = turn.get("question") or {}
            evaluation = turn.get("evaluation") or {}
            decision = turn.get("decision") or {}
            question_text = (
                turn.get("question_text")
                or _question_text(question)
            )
            score = (
                turn.get("overall_score")
                if turn.get("overall_score") is not None
                else evaluation.get("overall_score")
            )
            feedback = (
                turn.get("evaluation_summary")
                or _feedback_text(evaluation)
            )
            action = (
                turn.get("decision_action")
                or turn.get("routed_action")
                or decision.get("action")
                or ""
            )
            reason = turn.get("decision_reason") or decision.get("reason") or ""
            lines.extend(
                [
                    f"### Turn {index}",
                    "",
                    f"- Question: {question_text}",
                    f"- Answer: {turn.get('answer', '')}",
                    f"- Score: {_format_score(score)}/5",
                    f"- Feedback: {feedback}",
                    f"- Decision: {_decision_label(action)}",
                    f"- Reason: {reason}",
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"


def _save_interview_outputs(
    *,
    output_dir: Path,
    run_name: str,
    thread_id: str,
    started_at: datetime,
    runtime_seconds: float,
    resume_path: Path,
    job_path: Path,
    state: dict[str, Any],
    status: str,
    error: str | None = None,
) -> tuple[Path, Path, Path]:
    llm_calls = llm_client.get_call_trace()
    run_dir = output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "thread_id": thread_id,
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now().astimezone().isoformat(),
        "runtime_seconds": round(runtime_seconds, 4),
        "status": status,
        "resume_path": str(resume_path),
        "job_path": str(job_path),
        "tokens": _token_summary(llm_calls),
    }
    if error:
        metadata["error"] = error

    trace_payload = {
        "metadata": metadata,
        "workflow_trace": state.get("trace", []),
        "llm_calls": llm_calls,
        "document_brief": state.get("document_brief", {}),
        "planned_questions": state.get("planned_questions", []),
        "turn_summaries": state.get("turn_summaries", []),
        "turns": state.get("turns", []),
        "final_report": _model_dump(state.get("final_report")),
        "state_status": state.get("status"),
    }
    report_payload = {
        "metadata": metadata,
        "final_report": _model_dump(state.get("final_report")),
        "turn_summaries": state.get("turn_summaries", []),
    }

    trace_path = run_dir / "trace.json"
    report_json_path = run_dir / "report.json"
    report_md_path = run_dir / "report.md"
    _write_json(trace_path, trace_payload)
    _write_json(report_json_path, report_payload)
    report_md_path.write_text(
        _render_report_markdown(_jsonable(report_payload)),
        encoding="utf-8",
    )
    return trace_path, report_json_path, report_md_path


def run_interview_cli(args: argparse.Namespace) -> None:
    resume_path = _select_path(
        label="resume",
        provided_path=args.resume_path,
        folder=LLM_DIR,
        suffixes={".json"},
    )
    job_path = _select_path(
        label="job description",
        provided_path=args.job_path,
        folder=JOBS_DIR,
        suffixes={".txt"},
    )

    request_payload = _build_interview_request(
        resume_path=resume_path,
        job_path=job_path,
        interview_type=args.interview_type,
        difficulty=args.difficulty,
        question_count=args.question_count,
        max_followups_per_question=args.max_followups,
    )

    thread_id = args.thread_id or str(uuid4())
    started_at = datetime.now().astimezone()
    run_name = _interview_run_name(started_at, thread_id)
    recordings_dir = args.output_dir / run_name / "recordings"
    started = time.perf_counter()
    state: dict[str, Any] = {}
    status = "completed"
    error_message: str | None = None

    llm_client.reset_call_trace()

    try:
        print("\n[STATE] Current stage: generate_plan")
        state = start_interview(
            request_payload,
            thread_id=thread_id,
            debug_trace=True,
        )
        _print_interview_plan(state)

        while True:
            interrupt_payload = _extract_interrupt_payload(state)
            if state.get("status") == "completed" or state.get("final_report"):
                break

            if not interrupt_payload:
                raise RuntimeError(
                    "Workflow stopped without a question or final report."
                )

            question = (
                interrupt_payload.get("question")
                or state.get("current_question")
                or {}
            )
            print("\n[STATE] Current stage: ask_question")
            print(f"\n[QUESTION] {_question_text(question)}")

            try:
                answer_payload = _collect_answer_payload(
                    args,
                    recordings_dir=recordings_dir,
                )
            except Exception as exc:  # noqa: BLE001 - answer mode should fall back.
                print(f"[ANSWER MODE] {exc}")
                print("[ANSWER MODE] Falling back to typed text answer.")
                answer_payload = {
                    "answer": _collect_text_answer(),
                    "answer_source": "text_fallback",
                }

            if status == "stopped_by_user":
                break

            print("\n[STATE] Current stage: evaluate_answer")
            state = resume_interview(thread_id=thread_id, answer=answer_payload)
            _print_latest_turn_result(state)

        if state.get("final_report"):
            final_report = _model_dump(state["final_report"])
            print("\n[STATE] Current stage: final_report")
            print(
                "[REPORT] Recommendation: "
                f"{final_report.get('overall_recommendation', '')}"
            )
            print(f"[REPORT] Summary: {final_report.get('summary', '')}")
    except KeyboardInterrupt:
        status = "stopped_by_user"
        print("\n[STATE] Interview stopped by user.")
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        print(f"\n[ERROR] {error_message}")
    finally:
        runtime_seconds = time.perf_counter() - started
        trace_path, report_json_path, report_md_path = _save_interview_outputs(
            output_dir=args.output_dir,
            run_name=run_name,
            thread_id=thread_id,
            started_at=started_at,
            runtime_seconds=runtime_seconds,
            resume_path=resume_path,
            job_path=job_path,
            state=state,
            status=status,
            error=error_message,
        )
        print(f"\n[TRACE] Saved trace log to {trace_path}")
        print(f"[REPORT] Saved JSON report to {report_json_path}")
        print(f"[REPORT] Saved Markdown report to {report_md_path}")

    if status == "failed":
        raise SystemExit(1)


def _analyze_speech(result: Any, video_path: Path) -> dict[str, Any]:
    """Run fluency (from transcript) and voice (from audio) analysis.

    Fluency is pure-Python and always runs; voice analysis decodes the audio
    and uses Praat, so it is best-effort and never fails the transcription.
    """
    from app.speech_analysis import analyze_fluency, analyze_voice, decode_audio_mono

    analysis: dict[str, Any] = {}

    fluency = analyze_fluency(result.all_words())
    analysis["fluency"] = fluency.to_dict()
    print(
        "[FLUENCY] "
        f"rate {fluency.speech_rate_wpm} wpm | "
        f"pauses {fluency.pause_count} ({fluency.long_pause_count} long) | "
        f"fillers {fluency.filler_count} | "
        f"repeats {fluency.repetition_count} | "
        f"MLR {fluency.mean_length_of_run} words"
    )
    for warning in fluency.warnings:
        print(f"[FLUENCY] note: {warning}")

    try:
        samples, sample_rate = decode_audio_mono(str(video_path))
        voice = analyze_voice(samples, sample_rate)
        analysis["voice"] = voice.to_dict()
        print(
            "[VOICE] "
            f"steadiness {voice.tremor_label} | "
            f"F0 {voice.f0_mean_hz} Hz | "
            f"jitter {voice.jitter_local_pct}% | "
            f"shimmer {voice.shimmer_local_pct}%"
        )
        for indicator in voice.tremor_indicators:
            print(f"[VOICE] note: {indicator}")
    except Exception as exc:  # noqa: BLE001 - voice analysis is best-effort
        analysis["voice"] = {"error": str(exc)}
        print(f"[VOICE] Skipped voice analysis: {exc}")

    return analysis


def run_transcribe_cli(args: argparse.Namespace) -> None:
    from app.speech_analysis import has_audio_stream
    from app.transcription import VideoTranscriber

    video_path = _select_path(
        label="video",
        provided_path=args.input_path,
        folder=VIDEO_DIR,
        suffixes={".mp4", ".mov", ".avi", ".mkv"},
    )

    if not has_audio_stream(str(video_path)):
        raise SystemExit(
            f"No audio track found in {video_path}; nothing to transcribe."
        )

    print(f"\n[TRANSCRIBE] Loading model '{args.model}' and transcribing {video_path} ...")
    transcriber = VideoTranscriber(model_size=args.model)
    result = transcriber.transcribe(str(video_path), language=args.language)

    payload = result.to_dict()
    if not args.skip_analysis:
        payload.update(_analyze_speech(result, video_path))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    text_path = args.output_dir / f"{stem}.txt"
    json_path = args.output_dir / f"{stem}.json"

    text_path.write_text(result.text + "\n", encoding="utf-8")
    _write_json(json_path, payload)

    print(f"[TRANSCRIBE] Language: {result.language} | Duration: {result.duration_sec}s")
    print(f"[TRANSCRIBE] Transcript length: {len(result.text)} characters")
    print(f"[TRANSCRIBE] Saved text transcript to {text_path}")
    print(f"[TRANSCRIBE] Saved JSON transcript to {json_path}")

    if not result.text:
        print(
            "[TRANSCRIBE] Warning: empty transcript "
            "(the video may have no speech audio)."
        )


def _video_presentation_metrics(source_path: str | None) -> dict[str, Any] | None:
    """Run face/presentation analysis on the source video, best-effort."""
    if not source_path or not Path(source_path).exists():
        print("[EVALUATE] --with-video set but source video was not found; skipping face metrics.")
        return None

    try:
        from app.video_analysis import VideoAnalyzer

        result = VideoAnalyzer().analyze(video_path=source_path)
        return result.to_dict().get("video_presentation")
    except Exception as exc:  # noqa: BLE001 - face metrics are optional
        print(f"[EVALUATE] Skipped face metrics: {exc}")
        return None


def run_evaluate_answer_cli(args: argparse.Namespace) -> None:
    from app.agent import llm_client
    from app.agent.agent import InterviewAgent
    from app.agent.profile import build_evaluation_profile
    from app.graph.schemas import EvaluationRequest
    from app.speech_analysis import build_delivery_metrics

    if not args.transcript.exists():
        raise SystemExit(f"Transcript file does not exist: {args.transcript}")

    transcript = _read_json(args.transcript)
    student_answer = str(transcript.get("text") or "").strip()
    if not student_answer:
        raise SystemExit(
            f"Transcript {args.transcript} has no text to evaluate."
        )

    if args.question_file is not None:
        if not args.question_file.exists():
            raise SystemExit(f"Question file does not exist: {args.question_file}")
        question = args.question_file.read_text(encoding="utf-8").strip()
    else:
        question = (args.question or "").strip()
    if not question:
        raise SystemExit("Provide --question or --question-file.")

    resume_path = _select_path(
        label="resume",
        provided_path=args.resume_path,
        folder=LLM_DIR,
        suffixes={".json"},
    )
    job_path = _select_path(
        label="job description",
        provided_path=args.job_path,
        folder=JOBS_DIR,
        suffixes={".txt"},
    )

    video_metrics = (
        _video_presentation_metrics(transcript.get("source_path"))
        if args.with_video
        else None
    )
    delivery_metrics = build_delivery_metrics(transcript, video_metrics)

    payload: dict[str, Any] = {
        "resume": _read_json(resume_path),
        "question": question,
        "student_answer": student_answer,
        "expected_good_answer_points": list(args.expected or []),
        "delivery_metrics": delivery_metrics or None,
    }
    payload.update(_load_job_payload(job_path))
    request = EvaluationRequest.model_validate(payload)

    profile = build_evaluation_profile(request)
    cv_context = request.resume if request.resume is not None else request.cv_context
    job_context = (
        request.job_description
        if request.job_description is not None
        else request.job_description_context
    )

    llm_client.reset_call_trace()
    print(f"\n[EVALUATE] Scoring answer from {args.transcript} ...")
    result = InterviewAgent(profile).evaluate_answer_structured(
        cv_context=cv_context,
        job_description_context=job_context,
        question=request.question,
        expected_good_answer_points=request.expected_good_answer_points,
        student_answer=request.student_answer,
        delivery_metrics=request.delivery_metrics,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"{args.transcript.stem}_evaluation.json"
    _write_json(
        out_path,
        {
            "question": question,
            "transcript_path": str(args.transcript),
            "delivery_metrics": delivery_metrics,
            "evaluation": result,
            "llm_calls": llm_client.get_call_trace(),
        },
    )

    evaluation = _model_dump(result)
    print(
        "[EVALUATE] Overall score: "
        f"{_format_score(evaluation.get('overall_score'))}/5 "
        f"({evaluation.get('overall_rating', 'n/a')}) | "
        f"signal: {evaluation.get('hiring_signal', 'n/a')}"
    )
    delivery = evaluation.get("delivery_assessment") or {}
    if delivery:
        print(
            "[EVALUATE] Delivery: "
            f"fluency {delivery.get('fluency_rating', 'n/a')} | "
            f"voice {delivery.get('voice_steadiness', 'n/a')}"
        )
        if delivery.get("impact_on_communication"):
            print(f"[EVALUATE] {delivery['impact_on_communication']}")
    print(f"[EVALUATE] Saved evaluation to {out_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run app utilities.")
    subparsers = parser.add_subparsers(dest="command")

    interview_parser = subparsers.add_parser(
        "interview",
        help="Run an interactive interview from an LLM-ready resume and a JD.",
    )
    interview_parser.add_argument(
        "--resume-path",
        type=Path,
        default=None,
        help="Path to an LLM-ready resume JSON file.",
    )
    interview_parser.add_argument(
        "--job-path",
        type=Path,
        default=None,
        help="Path to a job description .txt file.",
    )
    interview_parser.add_argument(
        "--interview-type",
        default="technical",
        help="Interview type passed into the question-generation prompt.",
    )
    interview_parser.add_argument(
        "--difficulty",
        default=None,
        help="Optional difficulty level. If omitted, the LLM infers it.",
    )
    interview_parser.add_argument(
        "--question-count",
        type=int,
        default=None,
        help="Optional number of planned questions. Defaults to profile config.",
    )
    interview_parser.add_argument(
        "--max-followups",
        type=int,
        default=1,
        help="Maximum follow-up questions per planned question, capped by profile.",
    )
    interview_parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional stable LangGraph thread id for this interview run.",
    )
    interview_parser.add_argument(
        "--output-dir",
        type=Path,
        default=INTERVIEW_RUNS_DIR,
        help="Folder where trace logs and reports will be saved.",
    )
    interview_parser.add_argument(
        "--answer-mode",
        choices=(
            "ask",
            "text",
            "audio",
            "video",
            "record-audio",
            "record-video",
        ),
        default="ask",
        help="How to collect each answer. Default: ask before each answer.",
    )
    interview_parser.add_argument(
        "--transcription-language",
        default="en",
        help="Spoken language for audio/video transcription. Default: en.",
    )
    interview_parser.add_argument(
        "--transcription-model",
        default="small.en",
        help="faster-whisper model size for audio/video answers.",
    )
    interview_parser.add_argument(
        "--video-sample-every-n",
        type=int,
        default=10,
        help="Analyze every nth frame for video-file answer metrics.",
    )
    interview_parser.add_argument(
        "--record-seconds",
        type=int,
        default=60,
        help="Default recording duration in seconds for record modes.",
    )
    interview_parser.add_argument(
        "--record-sample-rate",
        type=int,
        default=16000,
        help="Microphone sample rate for record-audio mode.",
    )
    interview_parser.add_argument(
        "--camera-device",
        default=None,
        help=(
            "Optional macOS ffmpeg avfoundation camera device index/name "
            "for record-video mode."
        ),
    )
    interview_parser.add_argument(
        "--audio-device",
        default=None,
        help=(
            "Optional macOS ffmpeg avfoundation audio device index/name "
            "for record-video mode."
        ),
    )
    interview_parser.add_argument(
        "--keep-recordings",
        action="store_true",
        help="Keep temporary recordings instead of deleting them after processing.",
    )

    parse_parser = subparsers.add_parser(
        "parse-resume",
        help="Parse a resume PDF into Docling JSON.",
    )
    parse_parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=RAW_DIR / "resume1.pdf",
        help="Path to the resume PDF file.",
    )
    parse_parser.add_argument(
        "--output-dir",
        type=Path,
        default=PARSED_DIR,
        help="Folder where the parsed JSON file will be saved.",
    )

    normalize_parser = subparsers.add_parser(
        "normalize-resume",
        help="Normalize Docling resume JSON into the app resume schema.",
    )
    normalize_parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=PARSED_DIR / "resume1_parsed.json",
        help="Path to a raw Docling JSON file.",
    )
    normalize_parser.add_argument(
        "--output-dir",
        type=Path,
        default=LLM_DIR,
        help="Folder where the normalized JSON file will be saved.",
    )

    prepare_parser = subparsers.add_parser(
        "prepare-resume",
        help="Parse a resume PDF, then normalize the parsed JSON.",
    )
    prepare_parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=RAW_DIR / "resume1.pdf",
        help="Path to the resume PDF file.",
    )
    prepare_parser.add_argument(
        "--parsed-dir",
        type=Path,
        default=PARSED_DIR,
        help="Folder where the parsed JSON file will be saved.",
    )
    prepare_parser.add_argument(
        "--output-dir",
        type=Path,
        default=LLM_DIR,
        help="Folder where the normalized JSON file will be saved.",
    )

    workflow_parser = subparsers.add_parser(
        "show-workflow",
        help="Print the interview workflow as Mermaid text.",
    )
    workflow_parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional path where Mermaid text should be written.",
    )

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe a video file into text using local faster-whisper.",
    )
    transcribe_parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=None,
        help="Path to a video file. If omitted, choose one from data/video/.",
    )
    transcribe_parser.add_argument(
        "--language",
        default="en",
        help="Spoken language for transcription. Default: en.",
    )
    transcribe_parser.add_argument(
        "--model",
        default="small.en",
        help="faster-whisper model size (e.g. tiny.en, base.en, small.en, medium.en).",
    )
    transcribe_parser.add_argument(
        "--output-dir",
        type=Path,
        default=TRANSCRIPTS_DIR,
        help="Folder where the .txt and .json transcripts will be saved.",
    )
    transcribe_parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Only transcribe; skip fluency and voice-quality analysis.",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate-answer",
        help="Evaluate one answer from a transcript JSON, delivery-aware.",
    )
    evaluate_parser.add_argument(
        "--transcript",
        type=Path,
        required=True,
        help="Path to a transcript JSON produced by `transcribe`.",
    )
    evaluate_parser.add_argument(
        "--question",
        default=None,
        help="The interview question this answer responds to.",
    )
    evaluate_parser.add_argument(
        "--question-file",
        type=Path,
        default=None,
        help="Path to a text file holding the interview question.",
    )
    evaluate_parser.add_argument(
        "--resume-path",
        type=Path,
        default=None,
        help="LLM-ready resume JSON for grounding. Defaults to a file in data/resumes/llm/.",
    )
    evaluate_parser.add_argument(
        "--job-path",
        type=Path,
        default=None,
        help="Job description .txt for grounding. Defaults to a file in data/jobs/.",
    )
    evaluate_parser.add_argument(
        "--expected",
        action="append",
        default=None,
        help="Expected strong-answer signal (repeatable).",
    )
    evaluate_parser.add_argument(
        "--with-video",
        action="store_true",
        help="Also run face/presentation analysis on the source video.",
    )
    evaluate_parser.add_argument(
        "--output-dir",
        type=Path,
        default=ANSWER_EVALS_DIR,
        help="Folder where the evaluation JSON will be saved.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_arg_parser()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if not argv_list:
        argv_list = ["interview"]

    args = parser.parse_args(argv_list)

    if args.command == "interview":
        run_interview_cli(args)
        return

    if args.command == "parse-resume":
        if not args.input_path.exists():
            raise SystemExit(f"Input file does not exist: {args.input_path}")

        output_path = parse_pdf_to_json(args.input_path, args.output_dir)
        print(f"Saved parsed JSON to {output_path}")
        return

    if args.command == "normalize-resume":
        if not args.input_path.exists():
            raise SystemExit(f"Input file does not exist: {args.input_path}")

        output_path = save_llm_resume(args.input_path, args.output_dir)
        print(f"Saved LLM-ready resume JSON to {output_path}")
        return

    if args.command == "prepare-resume":
        if not args.input_path.exists():
            raise SystemExit(f"Input file does not exist: {args.input_path}")

        parsed_path = parse_pdf_to_json(args.input_path, args.parsed_dir)
        output_path = save_llm_resume(parsed_path, args.output_dir)
        print(f"Saved parsed JSON to {parsed_path}")
        print(f"Saved LLM-ready resume JSON to {output_path}")
        return

    if args.command == "transcribe":
        run_transcribe_cli(args)
        return

    if args.command == "evaluate-answer":
        run_evaluate_answer_cli(args)
        return

    if args.command == "show-workflow":
        mermaid_output = build_mermaid_workflow()
        if args.output_path is not None:
            args.output_path.write_text(mermaid_output, encoding="utf-8")
            print(f"Saved Mermaid workflow to {args.output_path}")
            return

        print(mermaid_output)
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
