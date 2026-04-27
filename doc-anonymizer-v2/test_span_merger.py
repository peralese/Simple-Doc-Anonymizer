#!/usr/bin/env python3
"""Unit tests for core/span_merger.py.

Run with: python test_span_merger.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.span_merger import merge_adjacent_spans


# ── Helpers ───────────────────────────────────────────────────────────────────

def _det(word: str, label: str, score: float, start: int, end: int = None) -> dict:
    return {
        "word":       word,
        "label":      label,
        "confidence": score,
        "start":      start,
        "end":        end if end is not None else start + len(word),
    }


def _run(name: str, fn):
    try:
        fn()
        print(f"  PASS  {name}")
        return True
    except AssertionError as exc:
        print(f"  FAIL  {name}: {exc}")
        return False
    except Exception as exc:
        print(f"  ERROR {name}: {exc}")
        return False


# ── Test cases ────────────────────────────────────────────────────────────────

def test_person_name_space_gap():
    """'Bob Martinez' split into 'Bob' + 'Martinez' (gap = 1 space)."""
    text = "Bob Martinez"
    dets = [
        _det("Bob",      "PRIVATE_PERSON", 0.990, 0,  3),
        _det("Martinez", "PRIVATE_PERSON", 0.970, 4, 12),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1, f"expected 1 span, got {len(result)}"
    assert result[0]["word"]       == "Bob Martinez"
    assert result[0]["label"]      == "PRIVATE_PERSON"
    assert result[0]["confidence"] == 0.990   # max(0.990, 0.970)
    assert result[0]["start"]      == 0
    assert result[0]["end"]        == 12


def test_email_dot_fragmentation():
    """'bob.martinez@acme.com' split at dot before TLD (gap = 0)."""
    text = "bob.martinez@acme.com"
    dets = [
        _det("bob.martinez@acme", "PRIVATE_EMAIL", 0.995,  0, 17),
        _det(".com",              "PRIVATE_EMAIL", 0.988, 17, 21),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1, f"expected 1 span, got {len(result)}"
    assert result[0]["word"]  == "bob.martinez@acme.com"
    assert result[0]["label"] == "PRIVATE_EMAIL"
    assert result[0]["confidence"] == 0.995


def test_phone_number_fragmentation():
    """'(555) 345-6789' split at last digit (gap = 0)."""
    text = "(555) 345-6789"
    dets = [
        _det("(555) 345-678", "PRIVATE_PHONE", 0.998,  0, 13),
        _det("9",             "PRIVATE_PHONE", 0.996, 13, 14),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1, f"expected 1 span, got {len(result)}"
    assert result[0]["word"]  == "(555) 345-6789"
    assert result[0]["label"] == "PRIVATE_PHONE"


def test_secret_key_hyphen_fragmentation():
    """'sk-a1b2c3d4' split at hyphen (gap = 0)."""
    text = "sk-a1b2c3d4"
    dets = [
        _det("sk",         "SECRET", 0.985,  0,  2),
        _det("-a1b2c3d4",  "SECRET", 0.991,  2, 11),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1, f"expected 1 span, got {len(result)}"
    assert result[0]["word"]       == "sk-a1b2c3d4"
    assert result[0]["label"]      == "SECRET"
    assert result[0]["confidence"] == 0.991   # max(0.985, 0.991)


def test_different_labels_not_merged():
    """Adjacent spans with different labels must not be merged."""
    text = "John secret123"
    dets = [
        _det("John",      "PRIVATE_PERSON", 0.99,  0,  4),
        _det("secret123", "SECRET",         0.95,  5, 14),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 2, f"expected 2 spans, got {len(result)}"
    assert result[0]["word"]  == "John"
    assert result[1]["word"]  == "secret123"


def test_same_label_far_apart_not_merged():
    """Same-label spans separated beyond gap_tolerance must stay separate."""
    text = "Alice Johnson lives far from Jane Smith"
    # gap between "Johnson" end (13) and "Jane" start (29) = 16 chars
    dets = [
        _det("Alice Johnson", "PRIVATE_PERSON", 0.99,  0, 13),
        _det("Jane Smith",    "PRIVATE_PERSON", 0.98, 29, 39),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 2, f"expected 2 spans, got {len(result)}"
    assert result[0]["word"] == "Alice Johnson"
    assert result[1]["word"] == "Jane Smith"


def test_empty_input():
    """Empty detection list must return empty list."""
    result = merge_adjacent_spans([], "any text here", gap_tolerance=2)
    assert result == [], f"expected [], got {result}"


def test_single_detection_passthrough():
    """A single detection is returned unchanged."""
    text = "Alice Johnson"
    dets = [_det("Alice Johnson", "PRIVATE_PERSON", 0.99, 0, 13)]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1
    assert result[0]["word"] == "Alice Johnson"


def test_zero_gap_tolerance_disables_bridging():
    """gap_tolerance=0 only merges truly adjacent spans (gap == 0)."""
    text = "Bob Martinez"
    dets = [
        _det("Bob",      "PRIVATE_PERSON", 0.99, 0,  3),
        _det("Martinez", "PRIVATE_PERSON", 0.97, 4, 12),
    ]
    # gap = 4 - 3 = 1; with gap_tolerance=0, 1 > 0 → should NOT merge
    result = merge_adjacent_spans(dets, text, gap_tolerance=0)
    assert len(result) == 2, f"expected 2 spans with gap_tolerance=0, got {len(result)}"


def test_three_way_merge():
    """Three consecutive same-label fragments merge into one span."""
    text = "carol.white@example.com"
    dets = [
        _det("carol",            "PRIVATE_EMAIL", 0.99,  0,  5),
        _det(".white@example",   "PRIVATE_EMAIL", 0.98,  5, 19),
        _det(".com",             "PRIVATE_EMAIL", 0.97, 19, 23),
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1, f"expected 1 span, got {len(result)}"
    assert result[0]["word"] == "carol.white@example.com"
    assert result[0]["confidence"] == 0.99


def test_preserves_unsorted_input():
    """Input in reverse order is sorted and merged correctly."""
    text = "Bob Martinez"
    dets = [
        _det("Martinez", "PRIVATE_PERSON", 0.97, 4, 12),  # deliberately second
        _det("Bob",      "PRIVATE_PERSON", 0.99, 0,  3),  # deliberately first
    ]
    result = merge_adjacent_spans(dets, text, gap_tolerance=2)
    assert len(result) == 1
    assert result[0]["word"] == "Bob Martinez"


# ── Runner ────────────────────────────────────────────────────────────────────

TESTS = [
    ("person name space gap",           test_person_name_space_gap),
    ("email dot fragmentation",         test_email_dot_fragmentation),
    ("phone number fragmentation",       test_phone_number_fragmentation),
    ("secret key hyphen fragmentation",  test_secret_key_hyphen_fragmentation),
    ("different labels not merged",      test_different_labels_not_merged),
    ("same label far apart not merged",  test_same_label_far_apart_not_merged),
    ("empty input",                      test_empty_input),
    ("single detection passthrough",     test_single_detection_passthrough),
    ("zero gap tolerance",               test_zero_gap_tolerance_disables_bridging),
    ("three-way merge",                  test_three_way_merge),
    ("preserves unsorted input",         test_preserves_unsorted_input),
]

if __name__ == "__main__":
    print(f"Running {len(TESTS)} span_merger tests...\n")
    passed = sum(_run(name, fn) for name, fn in TESTS)
    failed = len(TESTS) - passed
    print(f"\n{'─' * 40}")
    print(f"  {passed}/{len(TESTS)} passed", end="")
    if failed:
        print(f"  ·  {failed} FAILED")
        sys.exit(1)
    else:
        print("  ✓")
