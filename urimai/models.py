"""Core domain types.

The central modelling decision: an applicant fact is one of THREE states, not two.
Known-true, known-false, and *not yet asked*. Conflating the third with the second is
how eligibility tools quietly deny people benefits they are entitled to, so `Applicant`
stores every field as Optional and the engine treats `None` as UNKNOWN throughout.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    LIKELY = "likely_eligible"        # every rule satisfied on known facts
    POSSIBLE = "possibly_eligible"    # no rule failed, but facts are missing
    UNLIKELY = "unlikely"             # at least one rule definitively failed
    EXCLUDED = "excluded"             # an explicit exclusion clause fired


class Applicant(BaseModel):
    """A citizen profile. Every field optional — see module docstring."""

    age: Optional[int] = Field(default=None, ge=0, le=120)
    gender: Optional[Literal["male", "female", "other"]] = None
    marital_status: Optional[
        Literal["married", "widowed", "unmarried", "separated"]
    ] = None
    state: Optional[str] = None
    area_type: Optional[Literal["rural", "urban"]] = None

    annual_income: Optional[int] = Field(default=None, ge=0)
    is_bpl: Optional[bool] = None
    pays_income_tax: Optional[bool] = None

    is_farmer: Optional[bool] = None
    land_acres: Optional[float] = Field(default=None, ge=0)

    disability_percent: Optional[int] = Field(default=None, ge=0, le=100)

    is_student: Optional[bool] = None
    studied_in_govt_school: Optional[bool] = None

    has_lpg_connection: Optional[bool] = None
    owns_pucca_house: Optional[bool] = None

    household_size: Optional[int] = Field(default=None, ge=1)


class RuleOutcome(BaseModel):
    field: str
    satisfied: Optional[bool]      # None == unknown
    explanation_en: str
    explanation_ta: str


class SchemeResult(BaseModel):
    scheme_id: str
    name_en: str
    name_ta: str
    benefit_en: str
    benefit_ta: str
    verdict: Verdict
    verify_at_en: str
    verify_at_ta: str
    source: str
    outcomes: list[RuleOutcome] = []
    missing_fields: list[str] = []
    exclusion_reason_en: Optional[str] = None
    exclusion_reason_ta: Optional[str] = None


class Assessment(BaseModel):
    applicant: Applicant
    results: list[SchemeResult]
    follow_up_questions_en: list[str] = []
    follow_up_questions_ta: list[str] = []
    transcript: Optional[str] = None

    @property
    def actionable(self) -> list[SchemeResult]:
        return [
            r for r in self.results
            if r.verdict in (Verdict.LIKELY, Verdict.POSSIBLE)
        ]
