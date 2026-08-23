"""Audio -> text.

Two backends, tried in order:

1. A Whisper-compatible HTTP endpoint (Groq's whisper-large-v3 by default). Groq is
   the pragmatic choice here: whisper-large-v3 handles Tamil well and the hosted
   endpoint costs nothing to start with.
2. `faster-whisper` locally, if installed — no network, no key, useful offline and
   for anyone who does not want audio leaving the machine.

If neither is available the API layer returns 503 and says so. It never invents a
transcript, because a fabricated transcript here becomes a fabricated eligibility
result, which is the one failure this project cannot afford.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

DEFAULT_MODEL = "whisper-large-v3"
DEFAULT_BASE = "https://api.groq.com/openai/v1"

# Tamil by default: this is the audience. Set URIMAI_STT_LANG="" to auto-detect.
DEFAULT_LANG = os.getenv("URIMAI_STT_LANG", "ta")


class TranscriptionUnavailable(RuntimeError):
    """No backend is configured. Callers must surface this, not paper over it."""


def _api_key() -> Optional[str]:
    return os.getenv("URIMAI_STT_KEY") or os.getenv("URIMAI_API_KEY") or os.getenv("GROQ_API_KEY")


def transcribe_http(audio: bytes, filename: str = "audio.ogg") -> str:
    key = _api_key()
    if not key:
        raise TranscriptionUnavailable("no API key for hosted transcription")

    base = (os.getenv("URIMAI_STT_BASE") or DEFAULT_BASE).rstrip("/")
    model = os.getenv("URIMAI_STT_MODEL") or DEFAULT_MODEL

    data = {"model": model, "response_format": "json"}
    if DEFAULT_LANG:
        data["language"] = DEFAULT_LANG

    resp = httpx.post(
        f"{base}/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (filename, audio)},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json().get("text") or "").strip()


def transcribe_local(audio: bytes, filename: str = "audio.ogg") -> str:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise TranscriptionUnavailable("faster-whisper is not installed") from exc

    import tempfile
    from pathlib import Path

    size = os.getenv("URIMAI_STT_LOCAL_MODEL", "small")
    model = WhisperModel(size, device="cpu", compute_type="int8")

    suffix = Path(filename).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(audio)
        tmp = fh.name
    try:
        segments, _ = model.transcribe(tmp, language=DEFAULT_LANG or None)
        return " ".join(s.text for s in segments).strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def available() -> bool:
    if _api_key():
        return True
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(audio: bytes, filename: str = "audio.ogg") -> str:
    """Transcribe, preferring the hosted endpoint. Raises TranscriptionUnavailable
    when nothing is configured — deliberately, so the caller can 503 honestly."""
    if not audio:
        raise ValueError("empty audio payload")

    errors: list[str] = []
    for backend in (transcribe_http, transcribe_local):
        try:
            return backend(audio, filename)
        except TranscriptionUnavailable as exc:
            errors.append(str(exc))
        except Exception as exc:  # network/model failure — try the next backend
            errors.append(f"{backend.__name__}: {exc}")

    raise TranscriptionUnavailable("; ".join(errors))
