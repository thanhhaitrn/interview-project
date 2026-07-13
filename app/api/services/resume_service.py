"""Resume operations: upload+parse+normalize, list, load, save."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api import deps
from app.resume_system.parser import parse_pdf_to_json
from app.resume_system.resume_normalizer import save_llm_resume


def list_resumes() -> list[dict[str, Any]]:
    """Return a summary for every normalized resume on disk."""
    summaries: list[dict[str, Any]] = []
    if not deps.LLM_DIR.exists():
        return summaries

    for path in sorted(deps.LLM_DIR.glob("*.json")):
        try:
            data = deps.read_json(path)
        except (ValueError, OSError):
            continue
        candidate = data.get("candidate") or {}
        summaries.append(
            {
                "id": deps.resume_id_from_path(path),
                "full_name": candidate.get("full_name"),
                "headline": candidate.get("headline"),
            }
        )
    return summaries


def create_resume_from_pdf(resume_id: str, pdf_bytes: bytes) -> dict[str, Any]:
    """Persist an uploaded PDF, parse it, and normalize it to the LLM schema.

    Reuses ``parse_pdf_to_json`` and ``save_llm_resume`` so the web upload
    produces exactly the same artifacts as the CLI ``prepare-resume`` flow.
    """
    resume_id = deps.safe_id(resume_id)
    deps.ensure_dirs()

    raw_path = deps.RAW_DIR / f"{resume_id}.pdf"
    raw_path.write_bytes(pdf_bytes)

    parsed_path: Path = parse_pdf_to_json(raw_path, deps.PARSED_DIR)
    llm_path: Path = save_llm_resume(parsed_path, deps.LLM_DIR)

    data = deps.read_json(llm_path)
    return {"id": deps.resume_id_from_path(llm_path), "resume": data}


def save_resume(resume_id: str, resume: dict[str, Any]) -> dict[str, Any]:
    """Overwrite a normalized resume JSON (used by the edit page)."""
    path = deps.resume_path_from_id(resume_id)
    deps.write_json(path, resume)
    return resume
