#!/usr/bin/env python3
"""Doc Anonymizer — PII Redaction.

Supports two modes:
  Automated  : python anonymize.py --doc <path> --terms <path>
               Runs Stage 1 (pattern match) then Stage 2 (privacy filter) in one pass.

  Reviewed   : python anonymize.py --doc <path> --review <csv>
               Applies a human-reviewed CSV produced by doc-anonymizer-v2/detect.py.
               Stages 1 and 2 are bypassed — the human's decisions are authoritative.
"""

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

from core import pattern_matcher, privacy_filter, doc_reader, doc_writer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 60


def _banner(label: str) -> None:
    print(SEPARATOR)
    print("  Doc Anonymizer v2 — Two-Stage Pipeline")
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
    stem = p.stem
    ext = ".txt" if fmt == "pdf" else p.suffix
    return str(Path("output") / f"{stem}_redacted{ext}")


# ---------------------------------------------------------------------------
# Per-stage text processors
# ---------------------------------------------------------------------------

def _apply_stage1_to_text(text: str, terms: list[str], location: str = "") -> tuple[str, list[dict]]:
    return pattern_matcher.redact(text, terms, location=location)


def _apply_stage2_to_text(text: str, device: str, location: str = "") -> tuple[str, list[dict]]:
    return privacy_filter.redact(text, device=device, location=location)


# ---------------------------------------------------------------------------
# Format-specific stage runners — each stage takes/returns the same content type
# ---------------------------------------------------------------------------

def _stage1_text(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    text = payload["content"]
    result, log = _apply_stage1_to_text(text, terms)
    return result, log


def _stage2_text(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    result, log = _apply_stage2_to_text(content, device)
    return result, log


def _stage1_docx(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    paragraphs: list[str] = payload["content"]["paragraphs"]
    redacted: list[str] = []
    log: list[dict] = []
    for i, para in enumerate(paragraphs):
        result, para_log = _apply_stage1_to_text(para, terms, location=f"paragraph {i + 1}")
        redacted.append(result)
        log.extend(para_log)
    return redacted, log


def _stage2_docx(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    redacted: list[str] = []
    log: list[dict] = []
    for i, para in enumerate(content):
        result, para_log = _apply_stage2_to_text(para, device, location=f"paragraph {i + 1}")
        redacted.append(result)
        log.extend(para_log)
    return redacted, log


def _stage1_xlsx(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    sheets: dict[str, list[list]] = payload["content"]["sheets"]
    redacted_sheets: dict[str, list[list]] = {}
    log: list[dict] = []
    for sheet_name, rows in sheets.items():
        redacted_rows: list[list] = []
        for row in rows:
            redacted_row = []
            for (r, c, val) in row:
                if isinstance(val, str) and val.strip():
                    location = f"sheet='{sheet_name}' row={r} col={c}"
                    new_val, cell_log = _apply_stage1_to_text(val, terms, location=location)
                    redacted_row.append(new_val)
                    log.extend(cell_log)
                else:
                    redacted_row.append(val)
            redacted_rows.append(redacted_row)
        redacted_sheets[sheet_name] = redacted_rows
    return redacted_sheets, log


def _stage2_xlsx(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    redacted_sheets: dict[str, list[list]] = {}
    log: list[dict] = []
    orig_sheets = payload["content"]["sheets"]
    for sheet_name, redacted_rows in content.items():
        orig_rows = orig_sheets[sheet_name]
        new_rows: list[list] = []
        for orig_row, red_row in zip(orig_rows, redacted_rows):
            new_row = []
            for (r, c, _), val in zip(orig_row, red_row):
                if isinstance(val, str) and val.strip():
                    location = f"sheet='{sheet_name}' row={r} col={c}"
                    new_val, cell_log = _apply_stage2_to_text(val, device, location=location)
                    new_row.append(new_val)
                    log.extend(cell_log)
                else:
                    new_row.append(val)
            new_rows.append(new_row)
        redacted_sheets[sheet_name] = new_rows
    return redacted_sheets, log


def _stage1_csv(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    rows: list[list[str]] = payload["content"]
    redacted_rows: list[list[str]] = []
    log: list[dict] = []
    for r_idx, row in enumerate(rows):
        redacted_row = []
        for c_idx, val in enumerate(row):
            if val and val.strip():
                location = f"row={r_idx + 1} col={c_idx + 1}"
                new_val, cell_log = _apply_stage1_to_text(val, terms, location=location)
                redacted_row.append(new_val)
                log.extend(cell_log)
            else:
                redacted_row.append(val)
        redacted_rows.append(redacted_row)
    return redacted_rows, log


def _stage2_csv(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    redacted_rows: list[list[str]] = []
    log: list[dict] = []
    for r_idx, row in enumerate(content):
        redacted_row = []
        for c_idx, val in enumerate(row):
            if isinstance(val, str) and val.strip():
                location = f"row={r_idx + 1} col={c_idx + 1}"
                new_val, cell_log = _apply_stage2_to_text(val, device, location=location)
                redacted_row.append(new_val)
                log.extend(cell_log)
            else:
                redacted_row.append(val)
        redacted_rows.append(redacted_row)
    return redacted_rows, log


def _stage1_pdf(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    return _apply_stage1_to_text(payload["content"], terms)


def _stage2_pdf(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    return _apply_stage2_to_text(content, device)


def _stage1_pptx(payload: dict, terms: list[str]) -> tuple[Any, list[dict]]:
    slides_info: list[dict] = payload["content"]["slides"]
    redacted_slides: list[dict] = []
    log: list[dict] = []
    for slide_info in slides_info:
        redacted_shapes = []
        for shape_info in slide_info["shapes"]:
            redacted_paras = []
            for p_idx, para_text in enumerate(shape_info["paragraphs"]):
                location = (
                    f"slide={slide_info['slide_idx'] + 1} "
                    f"shape='{shape_info['shape_name']}' "
                    f"para={p_idx + 1}"
                )
                result, para_log = _apply_stage1_to_text(para_text, terms, location=location)
                redacted_paras.append(result)
                log.extend(para_log)
            redacted_shapes.append({**shape_info, "paragraphs": redacted_paras})
        redacted_slides.append({**slide_info, "shapes": redacted_shapes})
    return redacted_slides, log


def _stage2_pptx(content: Any, payload: dict, device: str) -> tuple[Any, list[dict]]:
    redacted_slides: list[dict] = []
    log: list[dict] = []
    for slide_info in content:
        redacted_shapes = []
        for shape_info in slide_info["shapes"]:
            redacted_paras = []
            for p_idx, para_text in enumerate(shape_info["paragraphs"]):
                location = (
                    f"slide={slide_info['slide_idx'] + 1} "
                    f"shape='{shape_info['shape_name']}' "
                    f"para={p_idx + 1}"
                )
                result, para_log = _apply_stage2_to_text(para_text, device, location=location)
                redacted_paras.append(result)
                log.extend(para_log)
            redacted_shapes.append({**shape_info, "paragraphs": redacted_paras})
        redacted_slides.append({**slide_info, "shapes": redacted_shapes})
    return redacted_slides, log


STAGE1_MAP = {
    "text": _stage1_text,
    "docx": _stage1_docx,
    "xlsx": _stage1_xlsx,
    "csv": _stage1_csv,
    "pdf": _stage1_pdf,
    "pptx": _stage1_pptx,
}

STAGE2_MAP = {
    "text": _stage2_text,
    "docx": _stage2_docx,
    "xlsx": _stage2_xlsx,
    "csv": _stage2_csv,
    "pdf": _stage2_pdf,
    "pptx": _stage2_pptx,
}


def _initial_content(payload: dict) -> Any:
    """Extract the writer-compatible content structure from a freshly-read payload."""
    fmt = payload["format"]
    if fmt in ("text", "pdf"):
        return payload["content"]
    elif fmt == "docx":
        return payload["content"]["paragraphs"]
    elif fmt == "xlsx":
        # Build flat redacted_sheets matching what the writer expects
        sheets = payload["content"]["sheets"]
        return {
            sn: [[val for (_r, _c, val) in row] for row in rows]
            for sn, rows in sheets.items()
        }
    elif fmt == "csv":
        return payload["content"]
    elif fmt == "pptx":
        return payload["content"]["slides"]
    else:
        return payload["content"]


# ---------------------------------------------------------------------------
# Human-reviewed mode helpers
# ---------------------------------------------------------------------------

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


def _apply_subs_to_text(text: str, subs: list[dict]) -> str:
    for sub in subs:
        text = re.sub(re.escape(sub["word"]), sub["replacement"], text, flags=re.IGNORECASE)
    return text


def _apply_review_to_content(fmt: str, content: Any, subs: list[dict]) -> tuple[Any, list[dict]]:
    """Apply CSV substitutions to the v1 content structure. Returns (new_content, log)."""
    log: list[dict] = []

    def _log_entry(sub: dict, location: str = "") -> dict:
        e = {
            "source":      "review_csv",
            "original":    sub["word"],
            "replacement": sub["replacement"],
            "label":       sub["label"],
            "confidence":  sub["confidence"],
        }
        if location:
            e["location"] = location
        return e

    if fmt in ("text", "pdf"):
        for sub in subs:
            if re.search(re.escape(sub["word"]), content, re.IGNORECASE):
                log.append(_log_entry(sub))
        return _apply_subs_to_text(content, subs), log

    elif fmt == "docx":
        new_paras: list[str] = []
        for i, para in enumerate(content):
            for sub in subs:
                if re.search(re.escape(sub["word"]), para, re.IGNORECASE):
                    log.append(_log_entry(sub, f"paragraph {i + 1}"))
            new_paras.append(_apply_subs_to_text(para, subs))
        return new_paras, log

    elif fmt == "xlsx":
        new_sheets: dict = {}
        for sheet_name, rows in content.items():
            new_rows: list[list] = []
            for row in rows:
                new_row: list = []
                for val in row:
                    if isinstance(val, str):
                        for sub in subs:
                            if re.search(re.escape(sub["word"]), val, re.IGNORECASE):
                                log.append(_log_entry(sub, sub.get("location", "")))
                        new_row.append(_apply_subs_to_text(val, subs))
                    else:
                        new_row.append(val)
                new_rows.append(new_row)
            new_sheets[sheet_name] = new_rows
        return new_sheets, log

    elif fmt == "csv":
        new_rows_csv: list[list[str]] = []
        for r_idx, row in enumerate(content):
            new_row_csv: list[str] = []
            for c_idx, val in enumerate(row):
                if isinstance(val, str):
                    for sub in subs:
                        if re.search(re.escape(sub["word"]), val, re.IGNORECASE):
                            log.append(_log_entry(sub, f"row={r_idx + 1} col={c_idx + 1}"))
                    new_row_csv.append(_apply_subs_to_text(val, subs))
                else:
                    new_row_csv.append(val)
            new_rows_csv.append(new_row_csv)
        return new_rows_csv, log

    elif fmt == "pptx":
        new_slides: list[dict] = []
        for slide_info in content:
            new_shapes: list[dict] = []
            for shape_info in slide_info["shapes"]:
                new_paras_pptx: list[str] = []
                for p_idx, para in enumerate(shape_info["paragraphs"]):
                    location = (
                        f"slide={slide_info['slide_idx'] + 1} "
                        f"shape='{shape_info['shape_name']}' "
                        f"para={p_idx + 1}"
                    )
                    for sub in subs:
                        if re.search(re.escape(sub["word"]), para, re.IGNORECASE):
                            log.append(_log_entry(sub, location))
                    new_paras_pptx.append(_apply_subs_to_text(para, subs))
                new_shapes.append({**shape_info, "paragraphs": new_paras_pptx})
            new_slides.append({**slide_info, "shapes": new_shapes})
        return new_slides, log

    return content, []


def _run_reviewed(args: argparse.Namespace, now_str: str) -> None:
    """Phase 2: apply a human-reviewed detect.py CSV to a document."""
    _banner(now_str)

    review_path = Path(args.review)
    if not review_path.exists():
        print(f"  ERROR: review file not found: {args.review}", file=sys.stderr)
        sys.exit(1)

    # Step 1 — Load review CSV
    _step(1, 3, f"Loading review file: {args.review}")
    redact_rows = _read_review_csv(args.review)
    _indent(f"{len(redact_rows)} REDACT row(s) loaded.")

    # Dedup by word (case-insensitive), longest-first; warn on conflicting replacements
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

    # Step 2 — Read document
    _step(2, 3, f"Reading document: {args.doc}")
    try:
        payload = doc_reader.read(args.doc)
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    fmt = payload["format"]
    current_content = _initial_content(payload)
    current_content, all_log = _apply_review_to_content(fmt, current_content, subs)

    # Step 3 — Write output
    output_path = args.output or _default_output_path(args.doc, fmt)
    _step(3, 3, f"Writing output: {output_path}")
    try:
        actual_output = doc_writer.write(payload, current_content, output_path)
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

    print(SEPARATOR)
    print("  SUMMARY")
    _summary_line("Mode", "human-reviewed CSV")
    _summary_line("Substitutions applied", str(len(subs)))
    _summary_line("Output", actual_output)
    _summary_line("Log", log_path)
    print(SEPARATOR)


# ---------------------------------------------------------------------------
# Log writer
# ---------------------------------------------------------------------------

def _write_log(source_doc: str, output_doc: str, all_log: list[dict], log_path: str) -> None:
    data = {
        "source_document": source_doc,
        "output_document": output_doc,
        "timestamp": datetime.now().isoformat(),
        "total_redactions": len(all_log),
        "redactions": all_log,
    }
    Path(log_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Doc Anonymizer v2 — Two-Stage PII Redaction Pipeline"
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

    # ── Reviewed mode: consume a human-edited detect.py CSV ─────────────────
    if args.review:
        _run_reviewed(args, now_str)
        return

    use_pattern = not args.no_pattern and args.terms is not None
    use_privacy = not args.pattern_only

    _banner(now_str)

    total_steps = 2 + (1 if use_pattern else 0) + (1 if use_privacy else 0)
    step = 0
    all_log: list[dict] = []

    # ── Step: Read ──────────────────────────────────────────────────────────
    step += 1
    _step(step, total_steps, f"Reading document: {args.doc}")
    try:
        payload = doc_reader.read(args.doc)
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    fmt = payload["format"]
    meta = payload["meta"]
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

    # Content flows through the two stages sequentially
    current_content: Any = _initial_content(payload)

    # ── Step: Stage 1 — Pattern Matcher ─────────────────────────────────────
    terms: list[str] = []
    s1_count = 0
    if use_pattern:
        step += 1
        _step(step, total_steps, f"Stage 1 — Pattern Matcher: {args.terms}")
        try:
            terms = pattern_matcher.load_terms(args.terms)
            _indent(f"Loaded {len(terms)} terms.")
        except Exception as exc:
            print(f"  ERROR loading terms: {exc}", file=sys.stderr)
            sys.exit(1)
        current_content, s1_log = STAGE1_MAP[fmt](payload, terms)
        all_log.extend(s1_log)
        s1_count = len(s1_log)
        _indent(f"{s1_count} replacement(s) made.")

    # ── Step: Stage 2 — Privacy Filter ──────────────────────────────────────
    s2_count = 0
    if use_privacy:
        step += 1
        _step(step, total_steps, f"Stage 2 — OpenAI Privacy Filter (device={args.device})")
        _indent("Loading model... (first run downloads ~2.8 GB, cached after)")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            loaded = privacy_filter.load_model(args.device)
        if not loaded:
            _indent("WARNING: Model unavailable — Stage 2 will be skipped.")
        else:
            current_content, s2_log = STAGE2_MAP[fmt](current_content, payload, args.device)
            all_log.extend(s2_log)
            s2_count = len(s2_log)
            _indent(f"{s2_count} additional PII span(s) detected and redacted.")

    # ── Step: Write ──────────────────────────────────────────────────────────
    step += 1
    output_path = args.output or _default_output_path(args.doc, fmt)
    _step(step, total_steps, f"Writing output: {output_path}")

    # For xlsx/docx/pptx, the writer needs the structure from payload but the
    # values from current_content. We pass payload for the workbook/doc objects
    # and current_content as the redacted values.
    try:
        actual_output = doc_writer.write(payload, current_content, output_path)
    except Exception as exc:
        print(f"  ERROR writing output: {exc}", file=sys.stderr)
        raise

    # Write log sidecar
    log_stem = Path(actual_output).stem.replace("_redacted", "")
    log_path = str(Path(actual_output).parent / f"{log_stem}_redacted.log.json")
    _write_log(args.doc, actual_output, all_log, log_path)

    if args.verbose and all_log:
        print()
        print("  Redaction Log:")
        for entry in all_log:
            print(f"    {json.dumps(entry)}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(SEPARATOR)
    print("  SUMMARY")
    if use_pattern:
        _summary_line("Stage 1 (pattern match)", f"{s1_count} replacement(s)")
    if use_privacy:
        _summary_line("Stage 2 (privacy filter)", f"{s2_count} replacement(s)")
    _summary_line("Total", str(s1_count + s2_count))
    _summary_line("Output", actual_output)
    _summary_line("Log", log_path)
    print(SEPARATOR)


if __name__ == "__main__":
    main()
