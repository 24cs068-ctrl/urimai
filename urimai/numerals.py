"""Tamil number words -> integers.

Why this exists: the heuristic extractor originally required DIGITS. That is fine for
typed input and wrong for the input this project is actually built for. People do not
speak digits — they say "அறுபத்தி ஐந்து", and Whisper faithfully writes the words down.
So every spoken age, acreage and income was parsed as absent.

This is the same failure shape as the original `\b`-after-`வயது` bug: an English-shaped
assumption that passes every English test while the feature is dead for Tamil speakers.

Scope is deliberately narrow: cardinals up to a few lakh, which covers age, acreage and
household income. Anything it cannot parse confidently returns None, because in this
project a missing fact becomes a follow-up question and a wrong fact denies a benefit.
"""

from __future__ import annotations

import re
from typing import Optional

# Units. Alternates cover sandhi-fused spellings, where the preceding tens stem
# swallows the leading vowel: இருபத்தி + இரண்டு -> இருபத்தியிரண்டு.
_UNITS: dict[str, int] = {
    "ஒன்று": 1, "தொன்று": 1, "யொன்று": 1,
    "இரண்டு": 2, "யிரண்டு": 2, "ரெண்டு": 2,
    "மூன்று": 3, "மும்மூன்று": 3,
    "நான்கு": 4, "நாலு": 4,
    "ஐந்து": 5, "தைந்து": 5, "யைந்து": 5,
    "ஆறு": 6, "தாறு": 6,
    "ஏழு": 7, "தேழு": 7,
    "எட்டு": 8, "தெட்டு": 8,
    "ஒன்பது": 9, "தொன்பது": 9,
}

_TEENS: dict[str, int] = {
    "பதினொன்று": 11, "பன்னிரண்டு": 12, "பதின்மூன்று": 13, "பதிமூன்று": 13,
    "பதினான்கு": 14, "பதினைந்து": 15, "பதினாறு": 16, "பதினேழு": 17,
    "பதினெட்டு": 18, "பத்தொன்பது": 19,
}

# Standalone tens.
_TENS: dict[str, int] = {
    "பத்து": 10, "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50,
    "அறுபது": 60, "எழுபது": 70, "எண்பது": 80, "தொண்ணூறு": 90,
}

# Combining stems: the form a ten takes when a unit follows it.
_TENS_STEMS: dict[str, int] = {
    "இருபத்தி": 20, "இருபத்து": 20, "இருபத்த": 20,
    "முப்பத்தி": 30, "முப்பத்து": 30, "முப்பத்த": 30,
    "நாற்பத்தி": 40, "நாற்பத்து": 40, "நாற்பத்த": 40,
    "ஐம்பத்தி": 50, "ஐம்பத்து": 50, "ஐம்பத்த": 50,
    "அறுபத்தி": 60, "அறுபத்து": 60, "அறுபத்த": 60,
    "எழுபத்தி": 70, "எழுபத்து": 70, "எழுபத்த": 70,
    "எண்பத்தி": 80, "எண்பத்து": 80, "எண்பத்த": 80,
    "தொண்ணூற்றி": 90, "தொண்ணூற்று": 90,
}

_SCALES: dict[str, int] = {
    "நூறு": 100, "நூற்று": 100, "இருநூறு": 200, "முந்நூறு": 300,
    "நானூறு": 400, "ஐந்நூறு": 500, "அறுநூறு": 600, "எழுநூறு": 700,
    "எண்ணூறு": 800, "தொள்ளாயிரம்": 900,
    "ஆயிரம்": 1000, "ஆயிரத்து": 1000,
    "லட்சம்": 100000, "லட்சத்து": 100000,
}

# Scale words fuse onto the preceding number: ஐம்பது + ஆயிரம் -> ஐம்பதாயிரம்.
_FUSED_THOUSANDS: dict[str, int] = {
    "பத்தாயிரம்": 10000, "இருபதாயிரம்": 20000, "முப்பதாயிரம்": 30000,
    "நாற்பதாயிரம்": 40000, "ஐம்பதாயிரம்": 50000, "அறுபதாயிரம்": 60000,
    "எழுபதாயிரம்": 70000, "எண்பதாயிரம்": 80000, "தொண்ணூறாயிரம்": 90000,
    "ஓராயிரம்": 1000, "ஈராயிரம்": 2000, "மூவாயிரம்": 3000,
    "நாலாயிரம்": 4000, "ஐயாயிரம்": 5000, "ஆறாயிரம்": 6000,
    "ஏழாயிரம்": 7000, "எட்டாயிரம்": 8000, "ஒன்பதாயிரம்": 9000,
}

_ALL: dict[str, int] = {}
for _d in (_FUSED_THOUSANDS, _SCALES, _TEENS, _TENS, _TENS_STEMS, _UNITS):
    for _k, _v in _d.items():
        _ALL.setdefault(_k, _v)

# Longest-first so இருபத்தி wins over a shorter prefix, and பத்தாயிரம் over பத்து.
_TOKEN_RE = re.compile("|".join(sorted((re.escape(k) for k in _ALL), key=len, reverse=True)))

_MULTIPLIERS = {100, 1000, 100000}


def tamil_words_to_int(text: str) -> Optional[int]:
    """Parse a run of Tamil cardinals. Returns None when nothing parses."""
    tokens = _TOKEN_RE.findall(text or "")
    if not tokens:
        return None

    total = 0
    current = 0
    for tok in tokens:
        val = _ALL[tok]
        if val in _MULTIPLIERS and tok not in _FUSED_THOUSANDS:
            current = (current or 1) * val
            if val >= 1000:
                total += current
                current = 0
        elif tok in _FUSED_THOUSANDS:
            total += val
        else:
            current += val
    return (total + current) or None


def parse_quantity(text: str) -> Optional[float]:
    """Digits if present, else Tamil words. Digits win: they are unambiguous."""
    if m := re.search(r"\d+(?:\.\d+)?", text or ""):
        return float(m.group(0))
    v = tamil_words_to_int(text)
    return float(v) if v is not None else None


_DIGIT_RE = re.compile(r"\d+(?:\.\d+)?")
# \s* not \s+: sandhi fuses cardinals with no space at all
# (இருபத்தி + இரண்டு -> இருபத்தியிரண்டு). Requiring whitespace split that into
# 20 and 2 as two separate quantities, and the nearer one won.
_WORD_RUN_RE = re.compile(
    r"(?:%s)(?:\s*(?:%s))*" % (_TOKEN_RE.pattern, _TOKEN_RE.pattern)
)


def find_quantities(text: str) -> list[tuple[int, int, float]]:
    """Every quantity in `text` as (start, end, value).

    Both notations are located, because voice gives words and typing gives digits:
    digit runs, and contiguous runs of Tamil cardinals.
    """
    out: list[tuple[int, int, float]] = []
    for m in _DIGIT_RE.finditer(text or ""):
        out.append((m.start(), m.end(), float(m.group(0))))
    for m in _WORD_RUN_RE.finditer(text or ""):
        if (v := tamil_words_to_int(m.group(0))) is not None:
            out.append((m.start(), m.end(), float(v)))
    return sorted(out)
