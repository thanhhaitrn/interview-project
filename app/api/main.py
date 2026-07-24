"""FastAPI application for Candidly.

Thin HTTP layer over the existing interview-agent logic (resume parsing,
question generation, answer evaluation, transcription). Run with::

    PYTHONPATH=. uvicorn app.api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import ensure_dirs
from app.api.routers import media, mock, practice, profiles, resumes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    yield


app = FastAPI(title="Candidly API", version="0.1.0", lifespan=lifespan)

# Allow the Vite dev server (and any extra origins via env) to call the API.
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra = os.getenv("FRONTEND_ORIGINS", "")
_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(resumes.router)
app.include_router(profiles.router)
app.include_router(practice.router)
app.include_router(mock.router)
app.include_router(media.router)
