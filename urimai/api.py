"""HTTP surface.

Two entry points that matter:
  POST /api/assess        {"text": "..."}   free text -> assessment
  POST /api/assess/audio  multipart file    voice note -> transcript -> assessment

Transcription is pluggable. With no Whisper backend configured the audio route returns
503 with an explicit message rather than pretending to have heard something.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .extract import get_extractor
from .models import Applicant, Assessment
from .rules import assess, load_schemes

app = FastAPI(
    title="Urimai",
    description="Voice-first welfare scheme eligibility screening for Tamil speakers.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DISCLAIMER_EN = (
    "This is a screening aid, not a decision. It cannot grant or deny any benefit. "
    "Confirm every result at the office named beside it."
)
DISCLAIMER_TA = (
    "இது ஒரு பரிந்துரை மட்டுமே, இறுதி முடிவு அல்ல. "
    "ஒவ்வொரு திட்டத்தையும் அதற்குரிய அலுவலகத்தில் உறுதிப்படுத்தவும்."
)


class TextRequest(BaseModel):
    text: str
    profile: Optional[Applicant] = None


class AssessResponse(BaseModel):
    assessment: Assessment
    disclaimer_en: str = DISCLAIMER_EN
    disclaimer_ta: str = DISCLAIMER_TA


def _merge(base: Optional[Applicant], extracted: Applicant) -> Applicant:
    """Caller-supplied facts win over extracted ones — a human answering a follow-up
    question is more reliable than a model re-reading the original sentence."""
    if base is None:
        return extracted
    merged = extracted.model_dump()
    for k, v in base.model_dump().items():
        if v is not None:
            merged[k] = v
    return Applicant(**merged)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "schemes": len(load_schemes())}


@app.get("/api/schemes")
def schemes() -> list[dict]:
    return [
        {
            "id": s["id"],
            "name_en": s["name_en"],
            "name_ta": s["name_ta"],
            "benefit_en": s["benefit_en"],
            "level": s["level"],
            "source": s["source"],
        }
        for s in load_schemes()
    ]


@app.post("/api/assess", response_model=AssessResponse)
def assess_text(req: TextRequest) -> AssessResponse:
    if not req.text.strip():
        raise HTTPException(400, "text must not be empty")
    extracted = get_extractor().extract(req.text)
    applicant = _merge(req.profile, extracted)
    return AssessResponse(assessment=assess(applicant, transcript=req.text))


@app.post("/api/assess/audio", response_model=AssessResponse)
async def assess_audio(file: UploadFile = File(...)) -> AssessResponse:
    try:
        from .transcribe import transcribe
    except ImportError:
        raise HTTPException(503, "No transcription backend installed. See README.")

    audio = await file.read()
    text = transcribe(audio, filename=file.filename or "audio.ogg")
    if not text:
        raise HTTPException(422, "Could not transcribe the audio.")
    applicant = get_extractor().extract(text)
    return AssessResponse(assessment=assess(applicant, transcript=text))
