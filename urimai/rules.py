"""Deterministic eligibility engine.

Design note, and the reason this is not simply an LLM prompt:

An LLM is used ONCE, upstream, to turn free Tamil speech into structured facts
(`extract.py`). Every eligibility decision after that point is made by the plain,
auditable, side-effect-free code in this module. The same profile always produces the
same verdict, each verdict can be traced to the exact rule that produced it, and the
result does not drift when a model is swapped or a temperature changes.

Benefits decisions affect people's income. They should be reproducible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from .models import (
    Applicant,
    Assessment,
    RuleOutcome,
    SchemeResult,
    Verdict,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.yaml"

# Human-readable prompts for facts we may need to ask about.
FIELD_QUESTIONS_EN: dict[str, str] = {
    "age": "How old are you?",
    "gender": "Are you male or female?",
    "marital_status": "Are you married, unmarried or widowed?",
    "state": "Which state do you live in?",
    "area_type": "Do you live in a village or a town?",
    "is_bpl": "Do you have a ration card for a below-poverty-line household?",
    "pays_income_tax": "Does anyone in your family pay income tax?",
    "is_farmer": "Do you or your family farm land?",
    "land_acres": "How much land do you own, in acres?",
    "disability_percent": "Do you have a disability certificate, and what percentage does it state?",
    "is_student": "Are you currently studying?",
    "studied_in_govt_school": "Did you study classes 6 to 12 in a government school?",
    "has_lpg_connection": "Do you already have a gas cylinder connection?",
    "owns_pucca_house": "Do you own a concrete (pucca) house?",
    "household_size": "How many people live in your household?",
}

FIELD_QUESTIONS_TA: dict[str, str] = {
    "age": "உங்கள் வயது என்ன?",
    "gender": "நீங்கள் ஆணா, பெண்ணா?",
    "marital_status": "நீங்கள் திருமணமானவரா, திருமணமாகாதவரா, அல்லது விதவையா?",
    "state": "நீங்கள் எந்த மாநிலத்தில் வசிக்கிறீர்கள்?",
    "area_type": "நீங்கள் கிராமத்தில் வசிக்கிறீர்களா, நகரத்திலா?",
    "is_bpl": "உங்களிடம் வறுமைக் கோட்டிற்குக் கீழ் உள்ள குடும்ப ரேஷன் அட்டை உள்ளதா?",
    "pays_income_tax": "உங்கள் குடும்பத்தில் யாராவது வருமான வரி செலுத்துகிறார்களா?",
    "is_farmer": "நீங்கள் அல்லது உங்கள் குடும்பம் விவசாயம் செய்கிறீர்களா?",
    "land_acres": "உங்களுக்கு எத்தனை ஏக்கர் நிலம் உள்ளது?",
    "disability_percent": "உங்களிடம் மாற்றுத்திறன் சான்றிதழ் உள்ளதா? எத்தனை சதவீதம்?",
    "is_student": "நீங்கள் தற்போது படிக்கிறீர்களா?",
    "studied_in_govt_school": "6 முதல் 12ஆம் வகுப்பு வரை அரசுப் பள்ளியில் படித்தீர்களா?",
    "has_lpg_connection": "உங்களிடம் ஏற்கனவே எரிவாயு இணைப்பு உள்ளதா?",
    "owns_pucca_house": "உங்களுக்குச் சொந்தமாக நிரந்தர (பக்கா) வீடு உள்ளதா?",
    "household_size": "உங்கள் வீட்டில் எத்தனை பேர் வசிக்கிறார்கள்?",
}


def load_schemes(path: Path | str | None = None) -> list[dict[str, Any]]:
    src = Path(path) if path else DATA_PATH
    with open(src, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["schemes"]


def _evaluate_condition(value: Any, cond: dict[str, Any]) -> Optional[bool]:
    """Return True/False, or None when the applicant fact is unknown.

    `None` propagating as unknown (rather than False) is the whole point — see
    the module docstring in models.py.
    """
    if value is None:
        return None

    if "min" in cond and value < cond["min"]:
        return False
    if "max" in cond and value > cond["max"]:
        return False
    if "eq" in cond and value != cond["eq"]:
        return False
    if "in" in cond and value not in cond["in"]:
        return False
    if cond.get("is_true") and value is not True:
        return False
    if cond.get("is_false") and value is not False:
        return False
    return True


def _describe(field: str, cond: dict[str, Any], satisfied: Optional[bool]) -> tuple[str, str]:
    if satisfied is None:
        return (
            f"Not known yet: {field}",
            f"இன்னும் தெரியவில்லை: {field}",
        )
    verb_en = "meets" if satisfied else "does not meet"
    verb_ta = "பூர்த்தி செய்கிறது" if satisfied else "பூர்த்தி செய்யவில்லை"
    bound = ", ".join(f"{k}={v}" for k, v in cond.items() if k != "field")
    return (f"{field} {verb_en} requirement ({bound})", f"{field}: {verb_ta} ({bound})")


def assess_scheme(applicant: Applicant, scheme: dict[str, Any]) -> SchemeResult:
    profile = applicant.model_dump()

    result = SchemeResult(
        scheme_id=scheme["id"],
        name_en=scheme["name_en"],
        name_ta=scheme["name_ta"],
        benefit_en=scheme["benefit_en"],
        benefit_ta=scheme["benefit_ta"],
        verdict=Verdict.POSSIBLE,
        verify_at_en=scheme["verify_at_en"],
        verify_at_ta=scheme["verify_at_ta"],
        source=scheme["source"],
    )

    # Exclusions are checked first and are absolute.
    for exc in scheme.get("exclusions", []) or []:
        field = exc["field"]
        if _evaluate_condition(profile.get(field), exc) is True:
            result.verdict = Verdict.EXCLUDED
            result.exclusion_reason_en = exc.get("reason_en", f"Excluded by {field}")
            result.exclusion_reason_ta = exc.get("reason_ta", f"விலக்கு: {field}")
            return result

    any_failed = False
    for cond in scheme.get("rules", []) or []:
        field = cond["field"]
        satisfied = _evaluate_condition(profile.get(field), cond)
        en, ta = _describe(field, cond, satisfied)
        result.outcomes.append(
            RuleOutcome(field=field, satisfied=satisfied, explanation_en=en, explanation_ta=ta)
        )
        if satisfied is False:
            any_failed = True
        elif satisfied is None:
            result.missing_fields.append(field)

    if any_failed:
        result.verdict = Verdict.UNLIKELY
    elif result.missing_fields:
        result.verdict = Verdict.POSSIBLE
    else:
        result.verdict = Verdict.LIKELY

    return result


def assess(
    applicant: Applicant,
    schemes: list[dict[str, Any]] | None = None,
    transcript: str | None = None,
) -> Assessment:
    catalogue = schemes if schemes is not None else load_schemes()
    results = [assess_scheme(applicant, s) for s in catalogue]

    # Ask only about facts that could still flip a scheme INTO eligibility, and ask
    # the highest-yield question first. A field blocking six schemes is worth more
    # than one blocking a single scheme — this is the difference between a usable
    # two-question conversation and an interrogation the caller abandons.
    blocking: dict[str, int] = {}
    for r in results:
        if r.verdict is Verdict.POSSIBLE:
            for f in r.missing_fields:
                blocking[f] = blocking.get(f, 0) + 1

    needed = sorted(blocking, key=lambda f: (-blocking[f], f))

    return Assessment(
        applicant=applicant,
        results=results,
        transcript=transcript,
        follow_up_questions_en=[FIELD_QUESTIONS_EN.get(f, f) for f in needed],
        follow_up_questions_ta=[FIELD_QUESTIONS_TA.get(f, f) for f in needed],
    )
