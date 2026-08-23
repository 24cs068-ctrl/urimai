r"""Extraction tests.

`test_tamil_age_is_extracted` is a regression guard. The original age pattern ended in
`\b`, which silently dropped every Tamil-stated age: "வயது" terminates in a combining
vowel mark that Python's `\w` does not classify as a word character, so the boundary
never matched. It failed quietly on exactly the users the project exists to serve.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from urimai.extract import HeuristicExtractor
from urimai.models import Applicant


def test_tamil_age_is_extracted():
    a = HeuristicExtractor().extract("எனக்கு 65 வயது")
    assert a.age == 65


def test_tamil_widow_detected():
    a = HeuristicExtractor().extract("நான் விதவை")
    assert a.marital_status == "widowed"
    assert a.gender == "female"


def test_english_land_and_farmer():
    a = HeuristicExtractor().extract("I have 2 acres of land")
    assert a.land_acres == 2.0
    assert a.is_farmer is True


def test_extractor_never_guesses():
    """Vague input must yield an empty profile, not invented facts."""
    a = HeuristicExtractor().extract("hello, I need some help please")
    assert a.model_dump(exclude_none=True) == {}


def test_implausible_age_rejected():
    a = HeuristicExtractor().extract("I am 999 years old")
    assert a.age is None


def test_disability_percent_bounded():
    a = HeuristicExtractor().extract("I have 80 percent disability")
    assert a.disability_percent == 80
