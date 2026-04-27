"""Stage 1: Pattern-based redaction using a user-supplied word list."""

import re
from pathlib import Path
from typing import Optional


def load_terms(terms_path: str) -> list[str]:
    """Load terms from a flat .txt file; lines starting with # are comments."""
    path = Path(terms_path)
    terms = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    # Sort longest-first to avoid partial replacements
    terms.sort(key=len, reverse=True)
    return terms


def redact(text: str, terms: list[str], location: str = "") -> tuple[str, list[dict]]:
    """
    Replace all occurrences of each term (case-insensitive) with [KNOWN_TERM].
    Returns (redacted_text, log_entries).
    """
    if not text or not terms:
        return text, []

    log: list[dict] = []
    result = text

    for term in terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        matches = pattern.findall(result)
        if matches:
            for match in matches:
                entry: dict = {
                    "source": "pattern",
                    "term": match,
                }
                if location:
                    entry["location"] = location
                log.append(entry)
            result = pattern.sub("[KNOWN_TERM]", result)

    return result, log
