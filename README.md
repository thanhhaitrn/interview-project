# AI Interview Agent

## Overview
This project now keeps the active application code under `app/`:
- Parsing resume PDFs
- Normalizing parsed resume output
- Running the interview agent graph
- Viewing normalized resume JSON in Streamlit

## Requirements

- Python 3.10+
- `streamlit`
- `docling`

Install dependencies:
```bash
pip install -r requirements.txt
```

## Web App (Candidly)

A web frontend that wraps the interview-agent logic. Phase 1 (MVP) covers
Resume setup, Interview profiles, and Practice mode (question generation,
text/recorded answers, AI Coach panel, answer scoring, and an end-of-session
report).

Backend (FastAPI), from the repo root:

```bash
./.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=. ./.venv/bin/uvicorn app.api.main:app --reload --port 8000
```

The API is documented at http://localhost:8000/docs. It uses the same Ollama
configuration as the CLI (`.env`), and reads/writes the same `data/` layout
(resumes in `data/resumes/llm/`, profiles in `data/profiles/`, practice history
in `data/practice_runs/`).

Frontend (Vite + React), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (the dev server proxies `/api` to the backend on
port 8000). Typical flow: **Resume** → upload & edit a resume → **Profiles** →
create a profile (job description + resume version) → **Practice** → answer the
generated questions (type or record), toggle **Show AI Coach** for suggested
bullets and an AI sample answer.

## Run

Parse a resume PDF:

```bash
python -m app.resume_system.parser data/resumes/raw/resume1.pdf --output-dir data/resumes/parsed
```

Normalize the parsed JSON:

```bash
python -m app.resume_system.resume_normalizer data/resumes/parsed/resume1_parsed.json --output-dir data/resumes/llm
```

Normalize from the app entrypoint:

```bash
python -m app.main normalize-resume data/resumes/parsed/resume1_parsed.json --output-dir data/resumes/llm
```

Or parse a PDF first, then normalize the parsed output:

```bash
python -m app.main prepare-resume data/resumes/raw/resume1.pdf
```

Show the interview graph workflow:

```bash
python -m app.main show-workflow
```

View the normalized JSON:

```bash
streamlit run view_parsed_resume.py
```


## Interview Question Generation and Evaluation
Local interview-agent project that generates interview questions and evaluates
candidate answers with one unified AI agent profile.

Input style:
- Preferred: structured `resume` + structured `job_description`
- Backward compatible: flat `cv_context` + `job_description_context`
- Optional advanced config:
  - `interview_config` for rubric-driven structured question generation
  - `evaluation_config` for weighted criteria, anchors, fairness, and evidence rules

## Structure

- `app/resume_system/`: parse PDFs and normalize Docling JSON into the app resume schema.
- `app/agent/`: prompt builders, LLM client, profile, and structured outputs.
- `app/graph/`: LangGraph interview workflow, schemas, state, and nodes.
- `app/main.py`: CLI for resume preparation, interactive interviews, and workflow inspection.
- `data/resumes/llm/`: LLM-ready resume JSON files used at runtime.
- `data/jobs/`: job description `.txt` files used at runtime.
- `tests/fixtures/`: structured request payloads used only by tests.

## Workflow Utilities

Print the workflow:

```bash
python -m app.main show-workflow
```

Save Mermaid text to a file:

```bash
python -m app.main show-workflow --output-path workflow.mmd
```

## Video Analysis Quick Test

Install OpenCV if needed:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Record a short webcam interview answer and print JSON analysis:

```bash
PYTHONPATH=. ./.venv/bin/python experiments/video_interview_terminal.py
```

When prompted, enter `y`. Temporary recordings are saved under
`runtime_uploads/temp_recordings/` and deleted after analysis unless you pass
`--keep-temp`.

Analyze an existing video instead:

```bash
PYTHONPATH=. ./.venv/bin/python experiments/video_interview_terminal.py --sample-every-n 5
```

When prompted, enter `n`, then paste the video path.

Live webcam face-detection debug test:

```bash
./.venv/bin/python experiments/face_camera_test.py --debug-raw
```

Link to measurements table: https://docs.google.com/document/d/1LsQhwQZJxvMVPBCeOIe63j1x1Hq3iidA3vKOKCjCyyk/edit?usp=sharing

## Video Transcription (mp4 -> text)

Convert a video interview answer into text with a local `faster-whisper`
model, so the transcript can be pasted into the interview evaluation.

```bash
PYTHONPATH=. ./.venv/bin/python -m app.main transcribe data/video/video2.mp4 --language en
```

Omit the path to pick a video interactively from `data/video/`. Transcripts are
saved to `data/transcripts/<name>.txt` (clean text) and
`data/transcripts/<name>.json` (language, duration, word-level segments, plus
the `fluency` and `voice` analysis below).

### Delivery analysis

By default `transcribe` also analyzes how the answer was delivered:

- `fluency` (from the transcript + word timestamps): speaking rate (wpm),
  pauses and long pauses, filler words (`um`, `uh`, `like`, `you know`, ...),
  word repetitions/stumbles, and mean length of run (words spoken between
  pauses). Note: Whisper tends to clean up `um`/`uh`, so filler counts are a
  lower bound.
- `voice` (from the audio signal, via Praat/`parselmouth`): pitch (F0) mean and
  variability, jitter, and shimmer, summarized as a `tremor_label`
  (`steady` / `mildly_unstable` / `shaky`) to gauge a trembling voice. Norms
  are derived from sustained vowels, so on running speech they are heuristic.

Pass `--skip-analysis` to only produce the transcript.

Notes:
- The first run downloads the model from Hugging Face (`small.en` ~244MB) and
  needs network access; later runs use the local cache.
- Use `--model tiny.en`/`base.en` for faster runs, or `--model medium.en` for
  higher accuracy.
- `faster-whisper` reads the MP4 directly, so no separate audio extraction or
  system `ffmpeg` binary is required.

### Delivery-aware answer evaluation

Score a single spoken answer with the LLM, grounded in both the transcript text
and the delivery metrics above:

```bash
PYTHONPATH=. ./.venv/bin/python -m app.main evaluate-answer \
  --transcript data/transcripts/video2.json \
  --question "Tell me about your copywriting background and a result you drove." \
  --resume-path data/resumes/llm/resume1_parsed_llm.json \
  --job-path data/jobs/sample.txt
```

The evaluation feeds `fluency` and `voice` into the prompt, so the
`Communication Clarity` score and a dedicated `delivery_assessment` reflect how
the answer was delivered (pace, pauses, fillers, vocal steadiness) without
penalizing accent or non-native pronunciation. Pass `--with-video` to also fold
in face/presentation metrics from the source video. Results are saved to
`data/answer_evaluations/<name>_evaluation.json`.

Structured-output LLM calls retry on failure (`OLLAMA_MAX_RETRIES`, default 2),
and answer scoring runs at temperature 0 for stable scores.
