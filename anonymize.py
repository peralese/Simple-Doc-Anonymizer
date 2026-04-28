#!/usr/bin/env python3
"""Doc Anonymizer — PII Redaction.

Supports two modes:
  Automated  : python anonymize.py --doc <path> --terms <path>
               Runs Stage 1 (pattern match) then Stage 2 (privacy filter) in one pass.

  Reviewed   : python anonymize.py --doc <path> --review <csv>
               Applies a human-reviewed CSV produced by detect.py.
               Stages 1 and 2 are bypassed — the human's decisions are authoritative.
"""

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

from core import pattern_matcher, privacy_filter, span_merger
from core.doc_reader import read_document
from core.doc_writer import write_document


# ── Console helpers ───────────────────────────────────────────────────────────

SEPARATOR = "=" * 60


def _banner(label: str) -> None:
    print(SEPARATOR)
    print("  Doc Anonymizer — PII Redaction Pipeline")
    print(f"  {label}")
    print(SEPARATOR)


def _step(n: int, total: int, msg: str) -> None:
    print(f"[{n}/{total}] {msg}")


def _indent(msg: str) -> None:
    print(f"      {msg}")


def _summary_line(label: str, value: str, width: int = 26) -> None:
    print(f"  {label:<{width}}: {value}")


def _default_output_path(doc_path: str, fmt: str) -> str:
    p = Path(doc_path)
    ext = ".txt" if fmt == "pdf" else p.suffix
    return str(Path("output") / f"{p.stem}_redacted{ext}")


# ── Review CSV helpers ────────────────────────────────────────────────────────

def _read_review_csv(path: str) -> list[dict]:
    """Read a detect.py review CSV; return only REDACT rows, warn on unknown actions."""
    import csv as _csv
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            action = row.get("action", "").strip().upper()
            if action == "REDACT":
                try:
                    conf = float(row.get("confidence") or 0.0)
                except ValueError:
                    conf = 0.0
                rows.append({
                    "word":        row.get("word", "").strip(),
                    "replacement": row.get("replacement", "").strip(),
                    "label":       row.get("label", "").strip(),
                    "confidence":  conf,
                    "location":    row.get("location", "").strip(),
                })
            elif action != "SKIP":
                print(
                    f"  Warning: review row {i} has unrecognised action "
                    f"{row.get('action')!r} (word={row.get('word')!r}) — skipping",
                    file=sys.stderr,
                )
    return rows


def _build_substitutions(rows: list[dict]) -> list[dict]:
    """Dedup by word (case-insensitive), sort longest-first. Warn on conflicts."""
    seen: dict[str, dict] = {}
    for row in rows:
        key = row["word"].lower()
        if key not in seen:
            seen[key] = row
        elif seen[key]["replacement"] != row["replacement"]:
            print(
                f"  Warning: conflicting replacements for {row['word']!r} — "
                f"using first seen: {seen[key]['replacement']!r}",
                file=sys.stderr,
            )
    return sorted(seen.values(), key=lambda r: len(r["word"]), reverse=True)


# ── Log writer ────────────────────────────────────────────────────────────────

def _write_log(source_doc: str, output_doc: str, all_log: list[dict], log_path: str) -> None:
    data = {
        "source_document": source_doc,
        "output_document": output_doc,
        "timestamp":       datetime.now().isoformat(),
        "total_redactions": len(all_log),
        "redactions":       all_log,
    }
    Path(log_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Doc Anonymizer — PII Redaction Pipeline"
    )
    parser.add_argument("--doc",          required=True,                  help="Path to input document")
    parser.add_argument("--review",        default=None,                   help="Path to human-reviewed detect.py CSV — bypasses Stage 1 and 2")
    parser.add_argument("--terms",         default=None,                   help="Path to terms file (Stage 1, automated mode only)")
    parser.add_argument("--output",        default=None,                   help="Output file path")
    parser.add_argument("--pattern-only",  action="store_true",            help="Skip Stage 2 (automated mode only)")
    parser.add_argument("--no-pattern",    action="store_true",            help="Skip Stage 1 (automated mode only)")
    parser.add_argument("--verbose",       action="store_true",            help="Print full redaction log")
    parser.add_argument("--device",        default="cpu", choices=["cpu", "cuda"])
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _banner(now_str)

    # ── Step: Read document ───────────────────────────────────────────────────
    total_steps = 3 if args.review else (2 + bool(not args.no_pattern and args.terms) + bool(not args.pattern_only))
    _step(1, total_steps, f"Reading document: {args.doc}")

    try:
        doc = read_document(args.doc)
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    fmt    = doc["format"]
    chunks = doc["chunks"]
    meta   = doc["meta"]

    if fmt == "xlsx":
        _indent(f"{meta['sheets']} sheet(s), {meta['cells']:,} cells scanned.")
    elif fmt == "docx":
        _indent(f"{meta['paragraphs']} paragraph(s).")
    elif fmt == "pdf":
        _indent(f"{meta['pages']} page(s). Output will be written as .txt.")
    elif fmt == "pptx":
        _indent(f"{meta['slides']} slide(s), {meta['text_shapes']} text shape(s).")
    elif fmt == "csv":
        _indent(f"{meta['rows']} row(s), {meta['cols']} column(s).")
    else:
        _indent(f"{meta.get('lines', '?')} line(s).")

    output_path = args.output or _default_output_path(args.doc, fmt)
    all_log: list[dict] = []
    step = 1

    if args.review:
        # ── Reviewed mode ─────────────────────────────────────────────────────
        step += 1
        _step(step, total_steps, f"Loading review file: {args.review}")
        review_rows = _read_review_csv(args.review)
        _indent(f"{len(review_rows)} REDACT row(s) loaded.")
        substitutions = _build_substitutions(review_rows)

        if args.verbose:
            for s in substitutions:
                _indent(f"{s['word']!r}  →  {s['replacement']!r}")

        for s in substitutions:
            all_log.append({
                "source":      "review_csv",
                "original":    s["word"],
                "replacement": s["replacement"],
                "label":       s.get("label", ""),
                "confidence":  s.get("confidence", 0.0),
                "location":    s.get("location", ""),
            })

    else:
        # ── Automated mode ────────────────────────────────────────────────────
        use_pattern = not args.no_pattern and args.terms is not None
        use_privacy = not args.pattern_only

        raw_subs: list[dict] = []   # accumulates (word, replacement, log_entry) tuples

        # Stage 1 — Pattern Matcher
        if use_pattern:
            step += 1
            _step(step, total_steps, f"Stage 1 — Pattern Matcher: {args.terms}")
            try:
                terms = pattern_matcher.load_terms(args.terms)
                _indent(f"Loaded {len(terms)} terms.")
            except Exception as exc:
                print(f"  ERROR loading terms: {exc}", file=sys.stderr)
                sys.exit(1)

            s1_count = 0
            for chunk in chunks:
                text, location = chunk["text"], chunk["location"]
                for term in terms:
                    for match in re.compile(re.escape(term), re.IGNORECASE).finditer(text):
                        raw_subs.append({"word": match.group(), "replacement": "[KNOWN_TERM]"})
                        all_log.append({"source": "pattern", "term": match.group(), "location": location})
                        s1_count += 1
            _indent(f"{s1_count} replacement(s) found.")

        # Stage 2 — Privacy Filter
        if use_privacy:
            step += 1
            _step(step, total_steps, f"Stage 2 — OpenAI Privacy Filter (device={args.device})")
            _indent("Loading model... (first run downloads ~2.8 GB, cached after)")

            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                loaded = privacy_filter.load_model(args.device)

            if not loaded:
                _indent("WARNING: Model unavailable — Stage 2 skipped.")
            else:
                s2_count = 0
                for chunk in chunks:
                    text, location = chunk["text"], chunk["location"]
                    if not text.strip():
                        continue
                    try:
                        raw_hits = privacy_filter.detect(text)
                    except RuntimeError as exc:
                        _indent(f"Warning: {exc} (skipping {location})")
                        continue

                    merged = span_merger.merge_adjacent_spans(raw_hits, text, gap_tolerance=2)
                    for hit in merged:
                        raw_subs.append({"word": hit["word"], "replacement": f"[{hit['label']}]"})
                        all_log.append({
                            "source":   "privacy_filter",
                            "original": hit["word"],
                            "label":    hit["label"],
                            "score":    hit["confidence"],
                            "location": location,
                        })
                        s2_count += 1
                _indent(f"{s2_count} PII span(s) detected and flagged.")

        substitutions = _build_substitutions(raw_subs)

    # ── Write output ──────────────────────────────────────────────────────────
    step += 1
    _step(step, total_steps, f"Writing output: {output_path}")
    Path("output").mkdir(exist_ok=True)

    try:
        actual_output = write_document(
            fmt=fmt,
            raw=doc["raw"],
            output_path=output_path,
            substitutions=substitutions,
            source_path=args.doc,
        )
    except Exception as exc:
        print(f"  ERROR writing output: {exc}", file=sys.stderr)
        raise

    log_stem = Path(actual_output).stem.replace("_redacted", "")
    log_path = str(Path(actual_output).parent / f"{log_stem}_redacted.log.json")
    _write_log(args.doc, actual_output, all_log, log_path)

    if args.verbose and all_log:
        print()
        print("  Redaction Log:")
        for entry in all_log:
            print(f"    {json.dumps(entry)}")

    # ── Summary ───────────────────────────────────────────────────────────────
    s1_total = sum(1 for e in all_log if e.get("source") == "pattern")
    s2_total = sum(1 for e in all_log if e.get("source") == "privacy_filter")
    rv_total = sum(1 for e in all_log if e.get("source") == "review_csv")

    print(SEPARATOR)
    print("  SUMMARY")
    if args.review:
        _summary_line("Mode",                 "human-reviewed CSV")
        _summary_line("Substitutions applied", str(len(substitutions)))
    else:
        if s1_total:
            _summary_line("Stage 1 (pattern match)", f"{s1_total} replacement(s)")
        if s2_total:
            _summary_line("Stage 2 (privacy filter)", f"{s2_total} replacement(s)")
        _summary_line("Total", str(s1_total + s2_total))
    _summary_line("Output",    actual_output)
    _summary_line("Log",       log_path)
    print(SEPARATOR)


if __name__ == "__main__":
    main()
