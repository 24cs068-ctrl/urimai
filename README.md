# Urimai (உரிமை)

**Voice-first welfare scheme eligibility screening for Tamil speakers.**

India runs hundreds of welfare schemes. The people they exist for are frequently the
least able to find them: eligibility lives in English PDFs behind web portals, and
reaching it assumes literacy, a smartphone, and the confidence to fill a form.

Urimai inverts that. A person sends a voice note in Tamil describing their situation in
their own words — *"I'm 65, I'm a widow, I have a small piece of land"* — and gets back a
plain-language list of the schemes they are likely to qualify for, what each one pays,
and the exact office where they can confirm it.

---

## What it does not do

This is a **screening aid, not a decision**. It cannot grant or deny anything, and it is
built so that it cannot pretend otherwise:

- Every verdict is `likely_eligible`, `possibly_eligible`, `unlikely` or `excluded` —
  never "you are entitled to this".
- Every scheme carries the office where a human confirms it.
- Every rule is a transcribed prior from public guidelines, and says so.

Getting this wrong has a real cost. Telling someone they qualify when they don't sends
them on a wasted trip they may have taken unpaid leave for.

---

## The two design decisions that matter

### 1. Unknown is not "no"

The naive version of this app models each fact as a boolean, and a person who hasn't yet
mentioned their ration card silently fails every BPL-gated scheme. That failure mode
lands hardest on exactly the users the project exists for.

So every applicant fact is three-valued — true, false, or **not yet asked** — and the
engine propagates unknowns to a verdict of `possibly_eligible` plus a follow-up question.
`test_unknown_is_not_false` pins this: an empty profile must never produce a definitive
rejection.

Follow-up questions are then ordered by **information gain** — the field blocking the most
schemes is asked first. For a 65-year-old widow, that surfaces the ration-card question
ahead of nine others, because it alone gates five schemes.

### 2. The model extracts; it does not decide

A language model is used exactly once, at the boundary, to turn free Tamil speech into a
typed form. Every eligibility decision downstream is made by ordinary, auditable,
deterministic code in `urimai/rules.py`.

The same profile always yields the same verdict, each verdict traces to the rule that
produced it, and nothing drifts when a model or temperature changes. The extraction
prompt is also instructed to **omit** anything it isn't confident about, because a missing
fact becomes a question, while a wrong fact silently denies someone a benefit.

---

## Running it

```bash
pip install -r requirements.txt
uvicorn urimai.api:app --reload      # http://127.0.0.1:8000/docs
pytest -q                            # 16 tests
```

No API key is required. Without one, extraction falls back to a conservative regex parser
that fills a field only on an unambiguous signal — degraded, but working and honest about
it. To enable LLM extraction:

```bash
export URIMAI_API_KEY=...            # Groq or any OpenAI-compatible endpoint
export URIMAI_MODEL=llama-3.3-70b-versatile
```

### API

| Route | Purpose |
|---|---|
| `POST /api/assess` | `{"text": "..."}` → assessment |
| `POST /api/assess/audio` | voice note → transcript → assessment |
| `GET /api/schemes` | the scheme catalogue |
| `GET /api/health` | liveness + scheme count |

The audio route returns **503 when no transcription backend is configured**, rather than
pretending to have heard something.

---

## Layout

```
urimai/
  models.py     three-valued applicant profile, verdicts
  rules.py      deterministic engine + question ranking
  extract.py    speech -> typed facts (LLM, with regex fallback)
  api.py        FastAPI surface
data/
  schemes.yaml  10 schemes, hand-curated eligibility priors
tests/          16 tests, including two regression guards
```

To add a scheme, edit `data/schemes.yaml` only — no code change is needed. Conditions
support `min`, `max`, `eq`, `in`, `is_true`, `is_false`, plus absolute `exclusions`.

---

## Two bugs worth recording

Both were found by testing, and both would have failed silently in production against the
exact users this serves:

1. **The widow pension accepted men.** The rules checked marital status but not gender, so
   a male applicant with unknown marital status surfaced as a widow-pension candidate.
   Guarded by `test_widow_pension_requires_female`.

2. **Tamil ages were dropped entirely.** The age pattern ended in `\b`, but `வயது` ends in
   a combining vowel mark that Python's `\w` does not classify as a word character, so the
   boundary never matched and every Tamil-stated age was discarded — while English ages
   parsed fine. Guarded by `test_tamil_age_is_extracted`.

The second one is the more instructive: an English-only test suite would have passed
completely while the feature was broken for its entire intended audience.

---

## Status and limits

- 16 tests passing; engine and API verified end-to-end with Tamil input.
- **The scheme data is a prior, not an authority.** 10 schemes are encoded; guidelines
  change and local implementation varies. Verify against the linked source before relying
  on any result.
- Transcription is pluggable and not yet wired to a default backend.
- Eligibility for SECC-based schemes (Ayushman Bharat) is approximated by a BPL flag; the
  real criteria are deprivation indicators this profile does not capture.
