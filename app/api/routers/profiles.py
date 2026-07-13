"""Interview profile endpoints (CRUD). A profile = job description + resume."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api import deps
from app.api.schemas_api import ProfileIn

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
def list_profiles() -> list[dict[str, Any]]:
    if not deps.PROFILES_DIR.exists():
        return []
    profiles: list[dict[str, Any]] = []
    for path in sorted(deps.PROFILES_DIR.glob("*.json")):
        try:
            profiles.append(deps.read_json(path))
        except (ValueError, OSError):
            continue
    return profiles


@router.post("")
def create_profile(payload: ProfileIn) -> dict[str, Any]:
    profile_id = deps.safe_id(payload.profile_id)
    path = deps.profile_path_from_id(profile_id)
    if path.exists():
        raise HTTPException(
            status_code=409, detail=f"Profile already exists: {profile_id}"
        )

    # The chosen resume version must exist.
    deps.load_resume_or_404(payload.resume_version)

    record = payload.model_dump()
    record["profile_id"] = profile_id
    record["created_at"] = _now()
    record["updated_at"] = record["created_at"]
    deps.write_json(path, record)
    return record


@router.get("/{profile_id}")
def get_profile(profile_id: str) -> dict[str, Any]:
    return deps.load_profile_or_404(profile_id)


@router.put("/{profile_id}")
def update_profile(profile_id: str, payload: ProfileIn) -> dict[str, Any]:
    existing = deps.load_profile_or_404(profile_id)
    deps.load_resume_or_404(payload.resume_version)

    record = payload.model_dump()
    record["profile_id"] = deps.safe_id(profile_id)
    record["created_at"] = existing.get("created_at") or _now()
    record["updated_at"] = _now()
    deps.write_json(deps.profile_path_from_id(profile_id), record)
    return record


@router.delete("/{profile_id}")
def delete_profile(profile_id: str) -> dict[str, str]:
    path = deps.profile_path_from_id(profile_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
    path.unlink()
    return {"status": "deleted", "id": profile_id}
