r"""Spoken-number tests.

These are regression guards for the second instance of the project's founding bug.
The original `\b`-after-`வயது` fault was fixed, but the age pattern still required
DIGITS — and speech never produces digits. Whisper writes "அறுபத்தி ஐந்து", so every
SPOKEN age was dropped just as silently as before, and the English-only suite still
passed. The lesson did not generalise until these tests existed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from urimai.extract import HeuristicExtractor
from urimai.numerals import find_quantities, tamil_words_to_int


def test_tamil_cardinals():
    assert tamil_words_to_int("ஐந்து") == 5
    assert tamil_words_to_int("பதினைந்து") == 15
    assert tamil_words_to_int("அறுபது") == 60
    assert tamil_words_to_int("அறுபத்தி ஐந்து") == 65


def test_sandhi_fused_compound():
    """இருபத்தி + இரண்டு fuses to இருபத்தியிரண்டு in natural speech."""
    assert tamil_words_to_int("இருபத்தியிரண்டு") == 22


def test_fused_thousands():
    assert tamil_words_to_int("ஐம்பதாயிரம்") == 50000


def test_non_numeric_text_returns_none():
    assert tamil_words_to_int("நான் ஒரு விதவை") is None
    assert tamil_words_to_int("") is None


def test_spoken_age_is_extracted():
    """The regression this whole module exists for."""
    a = HeuristicExtractor().extract("எனக்கு அறுபத்தி ஐந்து வயது")
    assert a.age == 65


def test_spoken_age_after_the_word_vayathu():
    a = HeuristicExtractor().extract("என் வயது இருபத்தியிரண்டு")
    assert a.age == 22


def test_digits_still_work():
    assert HeuristicExtractor().extract("எனக்கு 65 வயது").age == 65


def test_spoken_acreage():
    a = HeuristicExtractor().extract("என்னிடம் இரண்டு ஏக்கர் நிலம் இருக்கிறது")
    assert a.land_acres == 2.0
    assert a.is_farmer is True


def test_age_is_not_mistaken_for_income():
    """Whisper often returns no punctuation at all. Clause-splitting read the AGE as
    the income; a value must attach to its NEAREST label, not the first one."""
    a = HeuristicExtractor().extract(
        "என் வயது இருபத்தியிரண்டு நான் கல்லூரியில் படிக்கிறேன் "
        "என் குடும்ப வருமானம் ஐம்பதாயிரம் ரூபாய்"
    )
    assert a.age == 22
    assert a.annual_income == 50000


def test_tamil_state_is_extracted():
    r"""The ORIGINAL \b bug survived untouched in the state pattern: "தமிழ்நாடு" ends
    in the combining mark ு, so the trailing \b could never match."""
    assert HeuristicExtractor().extract("நான் தமிழ்நாடு").state == "TN"


def test_inflected_state_is_extracted():
    """Speech inflects the stem — nobody says the citation form out loud."""
    assert HeuristicExtractor().extract("நான் தமிழ்நாட்டில் வசிக்கிறேன்").state == "TN"


def test_find_quantities_locates_both_notations():
    spans = find_quantities("எனக்கு 65 வயது மற்றும் இரண்டு ஏக்கர்")
    assert 65.0 in [v for _, _, v in spans]
    assert 2.0 in [v for _, _, v in spans]


def test_still_never_guesses():
    a = HeuristicExtractor().extract("வணக்கம், எனக்கு உதவி வேண்டும்")
    assert a.age is None
    assert a.annual_income is None
