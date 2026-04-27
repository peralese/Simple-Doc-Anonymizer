# Doc Anonymizer — Human-in-the-Loop PII Redaction Pipeline

A local, offline-capable CLI tool that redacts Personally Identifiable Information (PII)
from documents. The pipeline has two modes:

| Mode | When to use |
|------|-------------|
| **Human-reviewed** (recommended) | Sensitive documents where false positives or missed PII have real consequences |
| **Automated** (quick pass) | Low-stakes documents, bulk processing, or when speed matters more than precision |

**All processing runs locally. No data leaves the machine.**

---

## Architecture: Human-in-the-Loop

```
doc-anonymizer-v2/detect.py          anonymize.py --review
  ↓                                      ↓
  Document → Privacy Filter → CSV  →  [HUMAN REVIEWS]  →  Redacted Document
                                                              + Audit Log
```

The [`openai/privacy-filter`](https://huggingface.co/openai/privacy-filter) model is a
**detector**, not a redactor. It returns detected PII spans with confidence scores.
A human reviews that output — confirming hits, rejecting false positives, adjusting
replacement tokens, adding anything missed — before `anonymize.py` applies the final
redactions. The human's decisions are authoritative; the model never re-runs in Phase 2.

This separation matters because:

- **False positives** (over-redaction) make documents meaningless
- **False negatives** (missed PII) can expose sensitive information
- The review file is a durable, auditable artifact you can store alongside the output

---

## Setup

```bash
# 1. Navigate to the project root
cd Simple-Doc-Anonymizer

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies (covers both detect.py and anonymize.py)
pip install -r requirements.txt
```

> **First run note**: Phase 1 downloads the `openai/privacy-filter` model (~2.8 GB) from
> HuggingFace on the first invocation. After that it is cached at
> `~/.cache/huggingface/hub/`. Phase 2 (`anonymize.py --review`) never re-downloads it.

---

## Human-Reviewed Workflow (Recommended)

### Phase 1 — Detect

Run the privacy filter against your document. Optionally supply a terms file for
known org-specific terms the model may miss.

```bash
python doc-anonymizer-v2/detect.py \
  --doc input/report.xlsx \
  --terms input/terms.txt \
  --threshold 0.85
```

Output: `output/report_review.csv`

**Flags:**

| Flag | Description |
|------|-------------|
| `--doc` | **Required.** Input document path |
| `--terms` | Optional. Supplemental terms file (see [Terms File](#terms-file)) |
| `--threshold` | Float 0–1. Detections below this score are pre-set to `SKIP` while still appearing in the review file. Default: `0.0` (write everything, let human decide). **Tip:** use `0.85` to pre-skip low-confidence hits |
| `--device` | `cpu` (default) or `cuda` |

---

### Human Review

Open `output/report_review.csv` in Excel, LibreOffice, or any CSV editor.

The file is sorted **confidence ascending** — uncertain detections appear first
because they need the most attention. High-confidence rows at the bottom need the
least review time.

| Column | What to do |
|--------|------------|
| `word` | The detected text — read-only reference |
| `label` | PII category detected by the model |
| `confidence` | 0.0–1.0. `1.0` = terms-file entry (known, not inferred) |
| `action` | **Edit this.** `REDACT` to apply, `SKIP` to exclude |
| `replacement` | **Edit this.** Change from generic `[PRIVATE_PERSON]` to something meaningful like `[EMPLOYEE-A]` or `[CLIENT]` |
| `location` | Where in the document (e.g. `Contacts!B4`, `Para 12`) — read-only reference |
| `notes` | Free-text for reviewer comments — ignored by `anonymize.py` |

Add rows for any PII the model missed — set `action=REDACT` and fill in `word` and
`replacement`. Save the file when done.

---

### Phase 2 — Redact

```bash
python anonymize.py \
  --doc input/report.xlsx \
  --review output/report_review.csv
```

`anonymize.py` reads the reviewed CSV, applies only rows marked `REDACT`, and writes
the redacted document and a JSON audit log. **It never re-runs the model.**

**Flags:**

| Flag | Description |
|------|-------------|
| `--doc` | **Required.** Original input document (same file used in detect.py) |
| `--review` | **Required.** Path to the human-edited review CSV |
| `--output` | Optional. Defaults to `output/<stem>_redacted<ext>` |
| `--verbose` | Print each substitution as it is applied |

---

## Automated Mode (Quick Pass)

Runs Stage 1 (pattern match) then Stage 2 (privacy filter) in a single unattended pass.
No human review step. Suitable for bulk processing or low-stakes documents.

```bash
python anonymize.py --doc input/report.xlsx --terms input/terms.txt
```

**Additional flags:**

| Flag | Description |
|------|-------------|
| `--pattern-only` | Skip Stage 2 (no model download required) |
| `--no-pattern` | Skip Stage 1 |
| `--device` | `cpu` (default) or `cuda` |

---

## End-to-End Example

```bash
# Phase 1: detect
python doc-anonymizer-v2/detect.py \
  --doc input/sample_document.xlsx \
  --terms input/terms.txt \
  --threshold 0.85

# ↓ Open output/sample_document_review.csv in a spreadsheet editor
# ↓ Change action=SKIP on false positives
# ↓ Edit replacements: [PRIVATE_PERSON] → [EMPLOYEE-A], etc.
# ↓ Add any rows the model missed
# ↓ Save

# Phase 2: redact
python anonymize.py \
  --doc input/sample_document.xlsx \
  --review output/sample_document_review.csv \
  --verbose

# Output: output/sample_document_redacted.xlsx
# Log:    output/sample_document_redacted.log.json
```

---

## Terms File

`input/terms.txt` — supplemental known terms the model may miss (project codes,
server names, client names). Detected terms are added to the review file with
`confidence=1.0` and `action=REDACT`, so the human can still override them.

Format: two columns, no header. Left column = text to find
(case-insensitive). Right column = replacement token.

```
Acme Corporation,[CLIENT]
Project Falcon,[PROJECT]
TIGERS,[SYSTEM]
PROD-DB-01,[SERVER-PROD]
```

> **Note:** The automated `anonymize.py --terms` mode uses a **single-column** terms
> file (one term per line) and replaces matches with `[KNOWN_TERM]`. The two-column
> format is for `detect.py` only.

---

## Supported File Formats

| Format | Read | Write | Notes |
|--------|------|-------|-------|
| `.txt`, `.md` | ✅ | ✅ | Plain text |
| `.docx` | ✅ | ✅ | Paragraph structure preserved |
| `.xlsx`, `.xls` | ✅ | ✅ | Cell-by-cell; formatting and sheet names preserved |
| `.csv` | ✅ | ✅ | Headers and structure preserved |
| `.pdf` | ✅ (extract) | ⚠️ as `.txt` | PDF write-back not supported |
| `.pptx` | ✅ | ✅ | All slides and shapes processed |

---

## Output Files

| File | Description |
|------|-------------|
| `output/<stem>_redacted<ext>` | Redacted document |
| `output/<stem>_redacted.log.json` | JSON audit log |
| `output/<stem>_review.csv` | Human-review file (Phase 1 output) |

### Audit log schema

```json
{
  "source_document": "input/report.xlsx",
  "output_document": "output/report_redacted.xlsx",
  "timestamp": "2026-04-27T09:45:00.000000",
  "total_redactions": 12,
  "redactions": [
    {
      "source": "review_csv",
      "original": "Alice Johnson",
      "replacement": "[EMPLOYEE-A]",
      "label": "PRIVATE_PERSON",
      "confidence": 0.997,
      "location": "Contacts!A2"
    }
  ]
}
```

---

## Project Structure

```
Simple-Doc-Anonymizer/
├── anonymize.py                  # Phase 2 CLI (also supports automated mode)
├── requirements.txt
├── README.md
├── core/
│   ├── pattern_matcher.py        # Automated mode Stage 1 — regex term replacement
│   ├── privacy_filter.py         # Automated mode Stage 2 — HuggingFace NER
│   ├── doc_reader.py             # Format-aware reader
│   └── doc_writer.py             # Format-aware writer
├── doc-anonymizer-v2/            # Phase 1 detection tool
│   ├── detect.py                 # Runs Privacy Filter → writes review CSV
│   ├── core/                     # Isolated core modules for detect.py
│   └── input/                    # Sample files for Phase 1
├── input/
│   ├── sample_document.txt       # Sample meeting notes with PII
│   ├── sample_document.xlsx      # Sample spreadsheet with PII
│   └── terms.txt                 # Org-specific terms (two-column format)
└── output/                       # All generated files land here
```

---

## Known Limitations

1. **PDF write-back not supported.** PDF output is extracted text saved as `.txt`.

2. **~96% model recall.** `openai/privacy-filter` has documented ~96% recall on its
   benchmark. It is **not a compliance tool**. The human review step exists precisely
   to catch the remaining 4%.

3. **Short cells / single words.** The privacy filter needs surrounding context.
   Isolated single-word cells may not be flagged — use the terms file for these cases.

4. **First run downloads ~2.8 GB.** The model is cached after the first download at
   `~/.cache/huggingface/hub/`.

5. **Non-English text.** The model was trained primarily on English. Performance on
   other languages is not guaranteed.

---

## Author

Erick Perales — IT Architect, Cloud Migration Specialist
