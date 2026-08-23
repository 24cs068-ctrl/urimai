"""Free speech -> structured facts.

This is the ONLY place a language model is allowed to influence the outcome, and even
here its job is narrow: read what the person said and fill in a typed form. It never
decides eligibility. If the model is unavailable, `HeuristicExtractor` keeps the demo
working offline — degraded, but honest about it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Protocol

import httpx

from .models import Applicant

SYSTEM_PROMPT = """You extract structured facts from a citizen describing their situation,
often in Tamil or Tanglish. Return ONLY a JSON object with any of these keys you can
determine with confidence:

age (int), gender ("male"|"female"|"other"),
marital_status ("married"|"widowed"|"unmarried"|"separated"),
state (2-letter code, e.g. "TN"), area_type ("rural"|"urban"),
annual_income (int rupees), is_bpl (bool), pays_income_tax (bool),
is_farmer (bool), land_acres (float), disability_percent (int),
is_student (bool), studied_in_govt_school (bool),
has_lpg_connection (bool), owns_pucca_house (bool), household_size (int)

CRITICAL: omit any key you are not confident about. Do NOT guess. A missing key means
"ask the person", which is safe. A wrong key silently denies someone a benefit.
Return the JSON object and nothing else."""


class Extractor(Protocol):
    def extract(self, text: str) -> Applicant: ...


class HeuristicExtractor:
    """Regex fallback. Deliberately conservative — it fills a field only on an
    unambiguous signal, because a wrong fact is worse than an absent one."""

    TAMIL_FEMALE = ("பெண", "மகள", "விதவை", "அம்மா")
    TAMIL_MALE = ("ஆண", "மகன")

    def extract(self, text: str) -> Applicant:
        t = text.lower()
        data: dict = {}

        # NOTE: no trailing \b here. Tamil "வயது" ends in a combining vowel mark,
        # which Python's \w does not treat as a word character, so \b would never
        # match and every Tamil age would be silently dropped.
        if m := re.search(r"(\d{1,3})\s*(?:years?|வயது|vayasu|age)", t):
            age = int(m.group(1))
            if 0 < age <= 120:
                data["age"] = age

        if any(w in text for w in self.TAMIL_FEMALE) or re.search(r"\b(female|woman|wife)\b", t):
            data["gender"] = "female"
        elif any(w in text for w in self.TAMIL_MALE) or re.search(r"\b(male|man|husband)\b", t):
            data["gender"] = "male"

        if "விதவை" in text or "widow" in t:
            data["marital_status"] = "widowed"

        if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:acres?|ஏக்கர்|ekkar)", t):
            data["land_acres"] = float(m.group(1))
            data["is_farmer"] = True
        elif re.search(r"\b(farmer|farming|விவசாய|vivasayam)\b", t):
            data["is_farmer"] = True

        if m := re.search(r"(\d{1,3})\s*(?:%|percent|சதவீத)", t):
            pct = int(m.group(1))
            if 0 <= pct <= 100:
                data["disability_percent"] = pct

        if re.search(r"\b(tamil ?nadu|தமிழ்நாடு|tn)\b", t):
            data["state"] = "TN"

        if re.search(r"\b(student|studying|படிக்கிற|college|school)\b", t):
            data["is_student"] = True

        return Applicant(**data)


class LLMExtractor:
    """Groq or any OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("URIMAI_API_KEY") or os.getenv("GROQ_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("URIMAI_BASE_URL")
            or "https://api.groq.com/openai/v1"
        ).rstrip("/")
        self.model = model or os.getenv("URIMAI_MODEL") or "llama-3.3-70b-versatile"
        self._fallback = HeuristicExtractor()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def extract(self, text: str) -> Applicant:
        if not self.available:
            return self._fallback.extract(text)
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                },
                timeout=30,
            )
            resp.raise_for_status()
            payload = json.loads(resp.json()["choices"][0]["message"]["content"])
            clean = {k: v for k, v in payload.items() if v is not None}
            return Applicant(**clean)
        except Exception:
            # Never fail the request because the model misbehaved.
            return self._fallback.extract(text)


def get_extractor() -> Extractor:
    llm = LLMExtractor()
    return llm if llm.available else HeuristicExtractor()
