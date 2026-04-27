"""Singleton wrapper for openai/privacy-filter (HuggingFace token-classification)."""

_pipeline = None
_load_attempted = False


def load_model(device: str = "cpu") -> None:
    """Load the model once and cache globally. Raises on failure."""
    global _pipeline, _load_attempted
    if _pipeline is not None:
        return
    if _load_attempted:
        raise RuntimeError(
            "Model failed to load on a previous attempt. "
            "Check that transformers and torch are installed correctly."
        )
    _load_attempted = True

    try:
        from transformers import pipeline as hf_pipeline
    except ImportError:
        raise ImportError(
            "Missing required packages. Install with:\n"
            "  pip install transformers torch"
        )

    _pipeline = hf_pipeline(
        task="token-classification",
        model="openai/privacy-filter",
        aggregation_strategy="simple",
        device=0 if device == "cuda" else -1,
    )


def detect(text: str) -> list[dict]:
    """
    Run the privacy filter on a text string.
    Returns a list of dicts: {word, label, confidence, start, end}.
    Raises RuntimeError if the model has not been loaded via load_model().
    """
    if not text or not text.strip():
        return []
    if _pipeline is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    try:
        entities = _pipeline(text)
    except Exception as exc:
        raise RuntimeError(f"Inference error: {exc}") from exc

    return [
        {
            "word": ent["word"],
            "label": ent["entity_group"],
            "confidence": round(float(ent["score"]), 4),
            "start": ent["start"],
            "end": ent["end"],
        }
        for ent in (entities or [])
    ]
