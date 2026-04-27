#!/usr/bin/env python3
"""Doc Anonymizer v2 — Phase 1: Run Privacy Filter, merge spans, write review CSV."""

import argparse
import re
import sys
from datetime import datetime
from itertools import groupby
from pathlib import Path

from core import span_merger
from core.doc_reader import read_document
from core.privacy_filter import detect, load_model
from core.review_file import write_review_csv


# ── Console helpers ───────────────────────────────────────────────────────────

def _rule():
    print("=" * 60)


def _banner(title: str):
    _rule()
    print(f"  Doc Anonymizer v2 — {title}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _rule()


def _meta_line(doc: dict) -> str:
    fmt  = doc["format"]
    meta = doc["meta"]
    if fmt == "xlsx":
        return f"      {meta['sheets']} sheet(s), {meta['cells']:,} cells loaded."
    if fmt == "text":
        return f"      {meta['lines']:,} line(s) loaded."
    if fmt == "docx":
        return f"      {meta['paragraphs']:,} paragraph(s) loaded."
    if fmt == "csv":
        return f"      {meta['rows']:,} row(s), {meta['cols']} column(s) loaded."
    if fmt == "pdf":
        return f"      {meta['pages']} page(s) loaded."
    if fmt == "pptx":
        return f"      {meta['slides']} slide(s), {meta['text_shapes']} text shape(s) loaded."
    return f"      {len(doc['chunks']):,} chunk(s) loaded."


# ── Terms-file helpers ────────────────────────────────────────────────────────

def _load_terms(path: str) -> list[dict]:
    """Parse two-column terms file: term,[REPLACEMENT] (one per line)."""
    terms: list[dict] = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",", 1)
            term        = parts[0].strip()
            replacement = parts[1].strip() if len(parts) > 1 else "[PRIVATE_TERM]"
            if term:
                terms.append({"term": term, "replacement": replacement})
    return terms


def _scan_terms(chunks: list[dict], terms: list[dict]) -> list[dict]:
    """Scan every chunk for known terms. Returns one detection per match."""
    detections: list[dict] = []
    for chunk in chunks:
        text     = chunk["text"]
        location = chunk["location"]
        for entry in terms:
            pattern = re.compile(re.escape(entry["term"]), re.IGNORECASE)
            for match in pattern.finditer(text):
                detections.append({
                    "word":        match.group(),
                    "label":       "PRIVATE_TERM",
                    "confidence":  1.0,
                    "start":       match.start(),
                    "end":         match.end(),
                    "action":      "REDACT",
                    "replacement": entry["replacement"],
                    "location":    location,
                    "notes":       "from terms file",
                })
    return detections


# ── Detection pass ────────────────────────────────────────────────────────────

def _run_detection_pass(
    chunks: list[dict],
    gap_tolerance: int,
    threshold: float,
) -> tuple[list[dict], int, dict[str, str]]:
    """
    Run privacy_filter.detect() + per-chunk span merge on every chunk.

    Returns:
        (raw_detections, total_raw_count, chunk_texts)
        raw_detections includes start/end for the subsequent global merge pass.
        chunk_texts maps location -> original chunk text.
    """
    raw_detections: list[dict] = []
    total_raw = 0
    chunk_texts: dict[str, str] = {}

    for chunk in chunks:
        text     = chunk["text"]
        location = chunk["location"]
        chunk_texts[location] = text

        if not text.strip():
            continue

        try:
            raw = detect(text)
        except RuntimeError as exc:
            print(f"      Warning: inference error at {location}: {exc}", file=sys.stderr)
            continue

        merged = span_merger.merge_adjacent_spans(raw, text, gap_tolerance)
        total_raw += len(raw)

        for hit in merged:
            action = "REDACT" if hit["confidence"] >= threshold else "SKIP"
            raw_detections.append({
                "word":        hit["word"],
                "label":       hit["label"],
                "confidence":  hit["confidence"],
                "start":       hit["start"],
                "end":         hit["end"],
                "action":      action,
                "replacement": f"[{hit['label']}]",
                "location":    location,
                "notes":       "" if action == "REDACT" else "below threshold",
            })

    return raw_detections, total_raw, chunk_texts


def _global_merge_pass(
    detections: list[dict],
    chunk_texts: dict[str, str],
    gap_tolerance: int,
    threshold: float,
) -> list[dict]:
    """
    Final safety pass: re-run span_merger within each location group.

    The per-chunk pass handles most fragmentation. This pass catches any
    remaining adjacent same-label spans — particularly relevant when a
    single chunk produced multiple overlapping detections that the first
    pass partially merged but left adjacent.
    """
    detections.sort(key=lambda d: (d["location"], d.get("start", 0)))
    result: list[dict] = []

    for location, group_iter in groupby(detections, key=lambda d: d["location"]):
        group     = list(group_iter)
        orig_text = chunk_texts.get(location, "")

        spans = [
            {
                "word":       d["word"],
                "label":      d["label"],
                "confidence": d["confidence"],
                "start":      d.get("start", 0),
                "end":        d.get("end", len(d["word"])),
            }
            for d in group
        ]
        merged = span_merger.merge_adjacent_spans(spans, orig_text, gap_tolerance)

        for span in merged:
            action = "REDACT" if span["confidence"] >= threshold else "SKIP"
            result.append({
                "word":        span["word"],
                "label":       span["label"],
                "confidence":  span["confidence"],
                "action":      action,
                "replacement": f"[{span['label']}]",
                "location":    location,
                "notes":       "" if action == "REDACT" else "below threshold",
            })

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Detect PII and write a human-review CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python detect.py --doc input/report.xlsx\n"
            "  python detect.py --doc input/notes.txt --terms input/terms.txt --threshold 0.85\n"
            "  python detect.py --doc input/report.xlsx --gap-tolerance 0\n"
        ),
    )
    parser.add_argument("--doc",           required=True,                   help="Input document path")
    parser.add_argument("--terms",                                           help="Supplemental terms file (term,replacement per line)")
    parser.add_argument("--threshold",     type=float,  default=0.0,        help="Confidence threshold; detections below are pre-set to SKIP (default: 0.0)")
    parser.add_argument("--device",        choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--gap-tolerance", type=int,    default=2,          help="Character gap for span merger (default: 2). Set to 0 to disable bridging.")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        print(f"Error: document not found: {args.doc}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    review_path = output_dir / f"{doc_path.stem}_review.csv"

    total_steps = 4 if args.terms else 3

    _banner("Phase 1: Detection")

    # ── Step 1: Read document ─────────────────────────────────────────────────
    print(f"[1/{total_steps}] Reading document: {args.doc}")
    try:
        doc = read_document(str(doc_path))
    except Exception as exc:
        print(f"Error reading document: {exc}", file=sys.stderr)
        sys.exit(1)

    chunks = doc["chunks"]
    print(_meta_line(doc))

    # ── Step 2: Privacy Filter + span merge ───────────────────────────────────
    print(f"[2/{total_steps}] Running OpenAI Privacy Filter (device={args.device})")
    print("      Loading model... (first run ~2.8 GB download, cached after)")

    try:
        load_model(args.device)
    except (ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    raw_detections, total_raw, chunk_texts = _run_detection_pass(
        chunks, args.gap_tolerance, args.threshold
    )

    # Global safety merge pass within each location group
    all_detections = _global_merge_pass(
        raw_detections, chunk_texts, args.gap_tolerance, args.threshold
    )

    total_after_merge    = len(all_detections)
    fragments_merged     = total_raw - total_after_merge

    print(f"      Raw detections : {total_raw}")
    print(f"      After merging  : {total_after_merge}"
          f"  ({fragments_merged} fragment{'s' if fragments_merged != 1 else ''} consolidated)")

    # ── Step 3: Terms file scan (optional) ───────────────────────────────────
    terms_count = 0
    if args.terms:
        terms_path = Path(args.terms)
        print(f"[3/{total_steps}] Scanning supplemental terms file: {args.terms}")
        if not terms_path.exists():
            print(f"  Warning: terms file not found: {args.terms}", file=sys.stderr)
        else:
            terms       = _load_terms(str(terms_path))
            term_hits   = _scan_terms(chunks, terms)
            terms_count = len(term_hits)
            all_detections.extend(term_hits)
            print(f"      {len(terms)} term(s) found, {terms_count} match(es) added.")

    # ── Step N: Write review CSV ──────────────────────────────────────────────
    print(f"[{total_steps}/{total_steps}] Writing review file: {review_path}")
    write_review_csv(all_detections, str(review_path))

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(all_detections)
    high  = sum(1 for d in all_detections if d["confidence"] >= 0.95)
    mid   = sum(1 for d in all_detections if 0.70 <= d["confidence"] < 0.95)
    low   = sum(1 for d in all_detections if d["confidence"] < 0.70 and d["label"] != "PRIVATE_TERM")

    _rule()
    print("  DETECTION SUMMARY")
    print(f"  Total detections    : {total}")
    print(f"  High confidence     : {high}  (>=0.95) — likely correct")
    print(f"  Medium confidence   : {mid}  (0.70–0.94) — review carefully")
    print(f"  Low confidence      : {low}   (<0.70) — probable false positives")
    print(f"  From terms file     : {terms_count}")
    print(f"  Fragments merged    : {fragments_merged}")
    print()
    print(f"  ⚠  Review {review_path} before running redact.py")
    print(f"  ⚠  Edit 'action' and 'replacement' columns as needed")
    print(f"  ⚠  Then run: python redact.py --doc {args.doc}")
    print(f"                                --review {review_path}")
    _rule()


if __name__ == "__main__":
    main()
