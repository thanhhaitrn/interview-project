"""Resume endpoints: list, upload+parse, get, update, delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api import deps
from app.api.services import resume_service
from app.graph.schemas import ResumeDocument

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.get("")
def list_resumes() -> list[dict[str, Any]]:
    return resume_service.list_resumes()


@router.post("")
async def create_resume(
    profile_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        return resume_service.create_resume_from_pdf(profile_id, pdf_bytes)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface parsing errors to client
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {exc}")


@router.get("/{resume_id}")
def get_resume(resume_id: str) -> dict[str, Any]:
    return deps.load_resume_or_404(resume_id)


@router.put("/{resume_id}")
def update_resume(resume_id: str, resume: ResumeDocument) -> dict[str, Any]:
    # Validate the shape, then persist the cleaned document.
    cleaned = resume.model_dump(exclude_none=True)
    return resume_service.save_resume(resume_id, cleaned)


@router.delete("/{resume_id}")
def delete_resume(resume_id: str) -> dict[str, str]:
    path = deps.resume_path_from_id(resume_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Resume not found: {resume_id}")
    path.unlink()
    return {"status": "deleted", "id": resume_id}
