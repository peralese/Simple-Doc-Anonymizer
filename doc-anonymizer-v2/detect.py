#!/usr/bin/env python3
"""Doc Anonymizer v2 — Phase 1: Run Privacy Filter and write a human-review CSV."""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

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
        return f"      {meta['sheets']} sheet(s), {meta['cells']:,} cells scanned."
    if fmt == "text":
        return f"      {meta['lines']:,} line(s) scanned."
    if fmt == "docx":
        return f"      {meta['paragraphs']:,} paragraph(s) scanned."
    if fmt == "csv":
        return f"      {meta['rows']:,} row(s), {meta['cols']} column(s) scanned."
    if fmt == "pdf":
        return f"      {meta['pages']} page(s) scanned."
    if fmt == "pptx":
        return f"      {meta['slides']} slide(s), {meta['text_shapes']} text shape(s) scanned."
    return f"      {len(doc['chunks']):,} chunk(s) scanned."


def _chunks_label(doc: dict) -> str:
    fmt  = doc["format"]
    meta = doc["meta"]
    if fmt == "xlsx":
        return f"{meta['cells']:,} cells"
    if fmt == "text":
        return f"{meta['lines']:,} lines"
    if fmt == "docx":
        return f"{meta['paragraphs']:,} paragraphs"
    if fmt == "pdf":
        return f"{len(doc['chunks']):,} lines"
    return f"{len(doc['chunks']):,} chunks"


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
                    "action":      "REDACT",
                    "replacement": entry["replacement"],
                    "location":    location,
                    "notes":       "from terms file",
                })
    return detections


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Detect PII and write a human-review CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python detect.py --doc input/report.xlsx\n"
            "  python detect.py --doc input/notes.txt --terms input/terms.txt --threshold 0.85\n"
            "  python detect.py --doc input/report.xlsx --device cuda\n"
        ),
    )
    parser.add_argument("--doc",       required=True,                      help="Input document path")
    parser.add_argument("--terms",                                          help="Supplemental terms file (term,replacement per line)")
    parser.add_argument("--threshold", type=float, default=0.0,            help="Confidence threshold; detections below are pre-set to SKIP (default: 0.0)")
    parser.add_argument("--device",    choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        print(f"Error: document not found: {args.doc}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    review_path = output_dir / f"{doc_path.stem}_review.csv"

    _banner("Phase 1: Detection")

    # ── Step 1: Read document ─────────────────────────────────────────────────
    print(f"[1/3] Reading document: {args.doc}")
    try:
        doc = read_document(str(doc_path))
    except Exception as exc:
        print(f"Error reading document: {exc}", file=sys.stderr)
        sys.exit(1)

    print(_meta_line(doc))
    chunks = doc["chunks"]

    # ── Step 2: Run Privacy Filter ────────────────────────────────────────────
    print(f"[2/3] Running OpenAI Privacy Filter (device={args.device})...")
    print("      Loading model... (first run downloads ~2.8 GB, cached after)")

    try:
        load_model(args.device)
    except (ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    all_detections: list[dict] = []
    for chunk in chunks:
        text = chunk["text"]
        if not text or not text.strip():
            continue
        try:
            hits = detect(text)
        except RuntimeError as exc:
            print(f"      Warning: {exc} (skipping {chunk['location']})", file=sys.stderr)
            continue

        for hit in hits:
            action = "REDACT" if hit["confidence"] >= args.threshold else "SKIP"
            all_detections.append({
                "word":        hit["word"],
                "label":       hit["label"],
                "confidence":  hit["confidence"],
                "action":      action,
                "replacement": f"[{hit['label']}]",
                "location":    chunk["location"],
                "notes":       "" if action == "REDACT" else "below threshold",
            })

    print(f"      {len(all_detections)} detection(s) across {_chunks_label(doc)}.")

    # ── Terms file scan ───────────────────────────────────────────────────────
    terms_count = 0
    if args.terms:
        terms_path = Path(args.terms)
        if not terms_path.exists():
            print(f"  Warning: terms file not found: {args.terms}", file=sys.stderr)
        else:
            terms      = _load_terms(str(terms_path))
            term_hits  = _scan_terms(chunks, terms)
            terms_count = len(term_hits)
            all_detections.extend(term_hits)

    # ── Step 3: Write review CSV ──────────────────────────────────────────────
    print(f"[3/3] Writing review file: {review_path}")
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
    print()
    print(f"  ⚠  Review {review_path} before running redact.py")
    print(f"  ⚠  Edit the 'action' and 'replacement' columns as needed")
    print(f"  ⚠  Then run: python redact.py --doc {args.doc}")
    print(f"                                --review {review_path}")
    _rule()


if __name__ == "__main__":
    main()
