"""Stage 2: Context-aware PII detection via openai/privacy-filter (HuggingFace)."""

import warnings
from typing import Optional

_pipeline = None
_load_attempted = False
_available = None


def _check_available() -> bool:
    global _available
    if _available is not None:
        return _available
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        _available = True
    except ImportError:
        _available = False
    return _available


def load_model(device: str = "cpu") -> bool:
    """
    Lazy-load the openai/privacy-filter model as a singleton.
    Returns True if the model loaded successfully.
    """
    global _pipeline, _load_attempted

    if _pipeline is not None:
        return True
    if _load_attempted:
        return False

    _load_attempted = True

    if not _check_available():
        warnings.warn(
            "Stage 2 skipped: 'transformers' and/or 'torch' are not installed. "
            "Run: pip install transformers torch",
            stacklevel=2,
        )
        return False

    from transformers import pipeline as hf_pipeline

    try:
        _pipeline = hf_pipeline(
            task="token-classification",
            model="openai/privacy-filter",
            aggregation_strategy="simple",
            device=0 if device == "cuda" else -1,
        )
        return True
    except Exception as exc:
        warnings.warn(f"Stage 2 skipped: failed to load privacy-filter model — {exc}", stacklevel=2)
        return False


def redact(
    text: str,
    device: str = "cpu",
    location: str = "",
) -> tuple[str, list[dict]]:
    """
    Run token-classification on text and replace detected PII spans with [LABEL].
    Returns (redacted_text, log_entries).
    """
    if not text or not text.strip():
        return text, []

    if not load_model(device):
        return text, []

    try:
        entities = _pipeline(text)  # type: ignore[misc]
    except Exception as exc:
        warnings.warn(f"Privacy filter inference error: {exc}", stacklevel=2)
        return text, []

    if not entities:
        return text, []

    log: list[dict] = []

    # Sort by start position descending so we can replace without offset drift
    entities_sorted = sorted(entities, key=lambda e: e["start"], reverse=True)

    result = text
    for ent in entities_sorted:
        start: int = ent["start"]
        end: int = ent["end"]
        label: str = ent["entity_group"]
        score: float = round(float(ent["score"]), 4)
        original: str = text[start:end]

        tag = f"[{label}]"
        result = result[:start] + tag + result[end:]

        entry: dict = {
            "source": "privacy_filter",
            "original": original,
            "label": label,
            "score": score,
        }
        if location:
            entry["location"] = location
        log.append(entry)

    return result, log
