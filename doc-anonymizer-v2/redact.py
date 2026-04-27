#!/usr/bin/env python3
"""Doc Anonymizer v2 — Phase 2: Apply human-reviewed redactions to a document."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.doc_reader import read_document
from core.doc_writer import write_document
from core.review_file import read_review_csv


# ── Console helpers ───────────────────────────────────────────────────────────

def _rule():
    print("=" * 60)


def _banner(title: str):
    _rule()
    print(f"  Doc Anonymizer v2 — {title}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _rule()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_occurrences(chunks: list[dict], word: str) -> int:
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return sum(len(pattern.findall(chunk["text"])) for chunk in chunks)


def _build_substitutions(redact_rows: list[dict], verbose: bool) -> list[dict]:
    """
    Deduplicate by word (case-insensitive), longest-first.
    Warns when the same word maps to different replacements — first entry wins.
    """
    seen: dict[str, dict] = {}
    for row in redact_rows:
        key = row["word"].lower()
        if key not in seen:
            seen[key] = row
        elif seen[key]["replacement"] != row["replacement"]:
            print(
                f"  Warning: conflicting replacements for {row['word']!r} — "
                f"using first seen: {seen[key]['replacement']!r}",
                file=sys.stderr,
            )

    subs = sorted(seen.values(), key=lambda r: len(r["word"]), reverse=True)

    if verbose:
        for sub in subs:
            print(f"      {sub['word']!r}  →  {sub['replacement']!r}")

    return subs


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Apply human-reviewed redactions to a document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python redact.py --doc input/report.xlsx --review output/report_review.csv\n"
            "  python redact.py --doc input/notes.txt --review output/notes_review.csv --verbose\n"
        ),
    )
    parser.add_argument("--doc",     required=True,              help="Original input document (same file used in detect.py)")
    parser.add_argument("--review",  required=True,              help="Path to the human-edited review CSV")
    parser.add_argument("--output",                              help="Output path (default: output/<stem>_redacted<ext>)")
    parser.add_argument("--verbose", action="store_true",        help="Print each substitution as it is applied")
    args = parser.parse_args()

    doc_path    = Path(args.doc)
    review_path = Path(args.review)

    if not doc_path.exists():
        print(f"Error: document not found: {args.doc}", file=sys.stderr)
        sys.exit(1)
    if not review_path.exists():
        print(f"Error: review file not found: {args.review}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_path = Path(args.output) if args.output else (
        output_dir / f"{doc_path.stem}_redacted{doc_path.suffix}"
    )
    log_path = output_dir / f"{doc_path.stem}_redacted.log.json"

    _banner("Phase 2: Redaction")

    # ── Step 1: Load review CSV ───────────────────────────────────────────────
    print(f"[1/3] Loading review file: {args.review}")
    all_rows     = read_review_csv(str(review_path))
    redact_rows  = [r for r in all_rows if r["action"] == "REDACT"]
    skip_rows    = [r for r in all_rows if r["action"] == "SKIP"]
    print(f"      {len(all_rows)} total rows — {len(redact_rows)} REDACT, {len(skip_rows)} SKIP")

    # ── Step 2: Read original document & build substitutions ─────────────────
    print(f"[2/3] Applying redactions to: {args.doc}")
    try:
        doc = read_document(str(doc_path))
    except Exception as exc:
        print(f"Error reading document: {exc}", file=sys.stderr)
        sys.exit(1)

    substitutions = _build_substitutions(redact_rows, args.verbose)

    # Count occurrences in original document for the audit log
    occurrences_map = {
        row["word"].lower(): _count_occurrences(doc["chunks"], row["word"])
        for row in substitutions
    }

    # ── Step 3: Write redacted document ──────────────────────────────────────
    print(f"[3/3] Writing output: {output_path}")
    try:
        actual_output = write_document(
            fmt=doc["format"],
            raw=doc["raw"],
            output_path=str(output_path),
            substitutions=substitutions,
            source_path=str(doc_path),
        )
    except Exception as exc:
        print(f"Error writing document: {exc}", file=sys.stderr)
        sys.exit(1)

    # Note PDF → .txt path change in log path base
    log_path = output_dir / f"{doc_path.stem}_redacted.log.json"

    # ── Write audit log ───────────────────────────────────────────────────────
    audit = {
        "source_document":  str(doc_path.resolve()),
        "review_file":      str(review_path.resolve()),
        "output_document":  str(Path(actual_output).resolve()),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "total_applied":    len(substitutions),
        "total_skipped":    len(skip_rows),
        "redactions": [
            {
                "word":        row["word"],
                "replacement": row["replacement"],
                "label":       row["label"],
                "confidence":  row["confidence"],
                "location":    row["location"],
                "occurrences": occurrences_map.get(row["word"].lower(), 0),
            }
            for row in substitutions
        ],
        "skipped": [
            {
                "word":       row["word"],
                "label":      row["label"],
                "confidence": row["confidence"],
                "reason":     "action=SKIP",
            }
            for row in skip_rows
        ],
    }
    log_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Summary ───────────────────────────────────────────────────────────────
    _rule()
    print("  REDACTION SUMMARY")
    print(f"  Applied  : {len(substitutions)} substitution(s)")
    print(f"  Skipped  : {len(skip_rows)} (action=SKIP)")
    print(f"  Output   : {actual_output}")
    print(f"  Audit log: {log_path}")
    _rule()


if __name__ == "__main__":
    main()
