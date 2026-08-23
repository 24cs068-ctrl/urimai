"""Engine tests.

These exist mainly to pin the three-valued logic. The bug that motivated the
`test_widow_pension_requires_female` case was real: the widow-pension rules originally
checked marital status but not gender, so a male applicant with unknown marital status
came back "possibly eligible".
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from urimai.models import Applicant, Verdict
from urimai.rules import assess, assess_scheme, load_schemes


@pytest.fixture(scope="module")
def schemes():
    return load_schemes()


def _by_id(results, scheme_id):
    return next(r for r in results if r.scheme_id == scheme_id)


def test_unknown_is_not_false(schemes):
    """An empty profile must never produce a definitive rejection."""
    result = assess(Applicant(), schemes)
    assert all(r.verdict is not Verdict.UNLIKELY for r in result.results)


def test_landholding_farmer_likely_for_pm_kisan(schemes):
    a = Applicant(is_farmer=True, land_acres=1.5)
    assert _by_id(assess(a, schemes).results, "pm-kisan").verdict is Verdict.LIKELY


def test_income_tax_payer_excluded_from_pm_kisan(schemes):
    a = Applicant(is_farmer=True, land_acres=1.5, pays_income_tax=True)
    r = _by_id(assess(a, schemes).results, "pm-kisan")
    assert r.verdict is Verdict.EXCLUDED
    assert r.exclusion_reason_en


def test_exclusion_beats_satisfied_rules(schemes):
    """Exclusions are absolute even when every positive rule passes."""
    a = Applicant(state="TN", gender="female", age=30, pays_income_tax=True)
    assert _by_id(assess(a, schemes).results, "tn-magalir-urimai").verdict is Verdict.EXCLUDED


def test_widow_pension_requires_female(schemes):
    """Regression: a male applicant must not surface as a widow-pension candidate."""
    a = Applicant(age=62, gender="male")
    assert _by_id(assess(a, schemes).results, "ignwps").verdict is Verdict.UNLIKELY


def test_age_below_bound_is_unlikely(schemes):
    a = Applicant(age=45, is_bpl=True)
    assert _by_id(assess(a, schemes).results, "ignoaps").verdict is Verdict.UNLIKELY


def test_missing_facts_become_questions(schemes):
    a = Applicant(age=65)
    result = assess(a, schemes)
    assert result.follow_up_questions_en
    assert result.follow_up_questions_ta
    assert len(result.follow_up_questions_en) == len(result.follow_up_questions_ta)


def test_no_duplicate_questions(schemes):
    result = assess(Applicant(), schemes)
    assert len(result.follow_up_questions_en) == len(set(result.follow_up_questions_en))


def test_every_scheme_declares_verification_route(schemes):
    """No scheme may tell a citizen they qualify without saying where to confirm."""
    for s in schemes:
        assert s.get("verify_at_en") and s.get("verify_at_ta")
        assert s.get("source", "").startswith("http")


def test_bilingual_parity(schemes):
    for s in schemes:
        assert s.get("name_ta") and s.get("benefit_ta")


def test_elderly_widow_not_offered_girls_scholarship(schemes):
    """Regression: an unknown `is_student` on a 65-year-old must not surface a
    scholarship aimed at girls entering higher education. Three-valued logic is
    correct in principle but produces absurd output without plausibility bounds,
    and one absurd row discredits the whole result set."""
    a = Applicant(age=65, gender="female", marital_status="widowed", state="TN")
    assert _by_id(assess(a, schemes).results, "tn-moovalur").verdict is Verdict.UNLIKELY
