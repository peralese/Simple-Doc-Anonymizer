"""Post-processing span merger for the openai/privacy-filter pipeline.

The transformer tokenizer creates subword tokens at punctuation boundaries
(. @ - _ space). Even with aggregation_strategy="max", adjacent fragments
with the same label can slip through as separate detections. Examples:

  "Bob Martinez"          → ["Bob", "Martinez"]          gap=1 (space)
  "bob.martinez@acme.com" → ["bob.martinez@acme", ".com"] gap=0
  "(555) 345-6789"        → ["(555) 345-678", "9"]        gap=0
  "sk-a1b2c3d4"           → ["sk", "-a1b2c3d4"]           gap=0

merge_adjacent_spans() consolidates these into single detections so the
human reviewer sees clean, complete entities rather than fragments.
"""


def merge_adjacent_spans(
    detections: list[dict],
    original_text: str,
    gap_tolerance: int = 2,
) -> list[dict]:
    """
    Merge consecutive same-label spans within gap_tolerance characters.

    Args:
        detections:    Detection list from privacy_filter.detect().
                       Each dict must have: word, label, confidence, start, end.
        original_text: The original text string the detections came from.
                       Used to reconstruct the exact merged word span from the
                       source text rather than concatenating word strings.
        gap_tolerance: Maximum character distance between end of one span and
                       start of the next for merging to occur (inclusive).
                       Default 2 handles single punctuation (. @ - _) and
                       space+punctuation combinations.
                       Set to 0 to only merge truly adjacent spans (gap == 0).

    Returns:
        Merged detection list sorted by start position. Consecutive same-label
        spans where next.start - current.end <= gap_tolerance are collapsed
        into one span. The merged span's confidence is max(a.confidence,
        b.confidence) — the most conservative (highest) score.
    """
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda d: d["start"])
    result: list[dict] = []
    current = dict(sorted_dets[0])

    for nxt in sorted_dets[1:]:
        gap = nxt["start"] - current["end"]
        if nxt["label"] == current["label"] and gap <= gap_tolerance:
            # Extend current span to absorb next span.
            # Use original_text to get the exact characters between spans.
            current["word"]       = original_text[current["start"]: nxt["end"]]
            current["end"]        = nxt["end"]
            current["confidence"] = max(current["confidence"], nxt["confidence"])
        else:
            result.append(current)
            current = dict(nxt)

    result.append(current)
    return result
