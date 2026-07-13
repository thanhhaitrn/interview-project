"""Shared paths, id helpers, and JSON file utilities for the web API.

The web layer persists everything as JSON files under ``data/`` so it matches
the existing on-disk layout used by the CLI (no database).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException

# --- Directories (mirror app/main.py and resume_system constants) -----------

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "resumes" / "raw"
PARSED_DIR = DATA_DIR / "resumes" / "parsed"
LLM_DIR = DATA_DIR / "resumes" / "llm"
JOBS_DIR = DATA_DIR / "jobs"
PROFILES_DIR = DATA_DIR / "profiles"
PRACTICE_RUNS_DIR = DATA_DIR / "practice_runs"
UPLOADS_DIR = DATA_DIR / "uploads"

LLM_SUFFIX = "_parsed_llm"

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def ensure_dirs() -> None:
    """Create every data directory the API reads from or writes to."""
    for directory in (
        RAW_DIR,
        PARSED_DIR,
        LLM_DIR,
        JOBS_DIR,
        PROFILES_DIR,
        PRACTICE_RUNS_DIR,
        UPLOADS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def safe_id(value: str) -> str:
    """Validate an id used in a file path to block traversal/odd characters."""
    value = (value or "").strip()
    if not value or not _SAFE_ID.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid id: {value!r}")
    return value


# --- JSON helpers -----------------------------------------------------------


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Resume id <-> path mapping --------------------------------------------
#
# A normalized resume lives at ``data/resumes/llm/<id>_parsed_llm.json``.
# The public "resume id" is the clean name (e.g. ``resume1`` or ``resume_DS``).


def resume_id_from_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith(LLM_SUFFIX):
        return stem[: -len(LLM_SUFFIX)]
    return stem


def resume_path_from_id(resume_id: str) -> Path:
    resume_id = safe_id(resume_id)
    candidate = LLM_DIR / f"{resume_id}{LLM_SUFFIX}.json"
    if candidate.exists():
        return candidate
    # Fallback for resumes saved without the parsed_llm convention.
    plain = LLM_DIR / f"{resume_id}.json"
    if plain.exists():
        return plain
    return candidate


def load_resume_or_404(resume_id: str) -> dict[str, Any]:
    path = resume_path_from_id(resume_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Resume not found: {resume_id}")
    return read_json(path)


# --- Profile id <-> path mapping -------------------------------------------


def profile_path_from_id(profile_id: str) -> Path:
    return PROFILES_DIR / f"{safe_id(profile_id)}.json"


def load_profile_or_404(profile_id: str) -> dict[str, Any]:
    path = profile_path_from_id(profile_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
    return read_json(path)
