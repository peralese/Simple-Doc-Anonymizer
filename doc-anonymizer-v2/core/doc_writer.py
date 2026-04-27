"""Format-aware document writer for doc-anonymizer-v2.

Applies a pre-built substitution list to the raw document object and writes
the result to disk. The caller is responsible for sorting substitutions
longest-word-first before passing them here.
"""

import re
from pathlib import Path


def write_document(
    fmt: str,
    raw,
    output_path: str,
    substitutions: list[dict],
    source_path: str = "",
) -> str:
    """
    Apply substitutions to raw and write to output_path.

    substitutions: list of {"word": str, "replacement": str},
                   must be sorted longest-word-first by caller.

    Returns the actual file path written (may differ for PDF → .txt).
    """
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "text":
        return _write_text(raw, p, substitutions)
    elif fmt == "docx":
        return _write_docx(raw, p, substitutions)
    elif fmt == "xlsx":
        return _write_xlsx(raw, p, substitutions)
    elif fmt == "csv":
        return _write_csv(raw, p, substitutions)
    elif fmt == "pdf":
        return _write_pdf_as_txt(raw, p, substitutions, source_path)
    elif fmt == "pptx":
        return _write_pptx(raw, p, substitutions)
    else:
        raise ValueError(f"Unsupported format: {fmt!r}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply(text: str, substitutions: list[dict]) -> str:
    """Apply all substitutions (case-insensitive) in longest-first order."""
    for sub in substitutions:
        text = re.sub(re.escape(sub["word"]), sub["replacement"], text, flags=re.IGNORECASE)
    return text


def _apply_to_para(para, substitutions: list[dict]) -> None:
    """Replace text in a docx/pptx paragraph. Preserves paragraph formatting;
    per-run character formatting is lost when text changes span multiple runs."""
    if not para.text.strip():
        return
    new_text = _apply(para.text, substitutions)
    if new_text == para.text:
        return
    # Put full new text into first run, blank the rest to avoid duplication.
    if para.runs:
        para.runs[0].text = new_text
        for run in para.runs[1:]:
            run.text = ""


# ── Format writers ────────────────────────────────────────────────────────────

def _write_text(text: str, p: Path, substitutions: list[dict]) -> str:
    p.write_text(_apply(text, substitutions), encoding="utf-8")
    return str(p)


def _write_docx(doc, p: Path, substitutions: list[dict]) -> str:
    for para in doc.paragraphs:
        _apply_to_para(para, substitutions)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _apply_to_para(para, substitutions)
    doc.save(str(p))
    return str(p)


def _write_xlsx(wb, p: Path, substitutions: list[dict]) -> str:
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None and isinstance(cell.value, str):
                    new_val = _apply(cell.value, substitutions)
                    if new_val != cell.value:
                        cell.value = new_val
    wb.save(str(p))
    return str(p)


def _write_csv(rows: list[list[str]], p: Path, substitutions: list[dict]) -> str:
    import csv

    new_rows = [[_apply(cell, substitutions) for cell in row] for row in rows]
    with p.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(new_rows)
    return str(p)


def _write_pdf_as_txt(full_text: str, p: Path, substitutions: list[dict], source_path: str) -> str:
    # PDF write-back is not supported — emit redacted content as .txt instead.
    txt_path = p.with_suffix(".txt")
    header = (
        "# NOTE: PDF write-back is not supported.\n"
        f"# Source: {source_path}\n"
        "# Redacted text content follows.\n\n"
    )
    txt_path.write_text(header + _apply(full_text, substitutions), encoding="utf-8")
    return str(txt_path)


def _write_pptx(prs, p: Path, substitutions: list[dict]) -> str:
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                _apply_to_para(para, substitutions)
    prs.save(str(p))
    return str(p)
