# Doc Anonymizer v2

A two-phase, human-in-the-loop document anonymization pipeline powered by the
[openai/privacy-filter](https://huggingface.co/openai/privacy-filter) model from HuggingFace.

---

## Philosophy: Why Human-in-the-Loop?

The OpenAI Privacy Filter is a **detector**, not a redactor. It returns a list of
detected PII spans with confidence scores. No automated system is perfect:

- **False positives** (over-redaction): "March" flagged as a person's name;
  "Chicago Bulls" redacted as an address.
- **False negatives** (missed PII): an unusual API key format the model hasn't seen;
  internal project codenames that are sensitive but not universally "private."

Both failure modes have real consequences. Over-redaction can make a document
meaningless; under-redaction can expose sensitive information.

This tool deliberately separates detection from redaction with a human review step
between them. The human confirms hits, rejects false positives, adjusts replacements
to meaningful tokens, and adds anything the model missed — then the redaction script
runs. The human's decisions are authoritative; `redact.py` never re-runs the model.

---

## Architecture

```
Phase 1 — detect.py
  Document → Privacy Filter → review CSV  ← HUMAN EDITS THIS
                                                    ↓
Phase 2 — redact.py
  Document + reviewed CSV → Redacted document + Audit log
```

Detection and redaction are intentionally **separate scripts** so that:

1. The human review file is a first-class artifact, not a transient state.
2. `redact.py` can be re-run with a corrected review file without re-downloading or
   re-running the model (which takes time and money).
3. The workflow is auditable: you can compare the original review file and the final
   audit log to show exactly what a human approved.

---

## Understanding Confidence Scores

| Range       | Meaning                                      | Default action |
|-------------|----------------------------------------------|----------------|
| ≥ 0.95      | High confidence — likely PII                 | REDACT         |
| 0.70 – 0.94 | Medium confidence — review carefully         | REDACT         |
| < 0.70      | Low confidence — probable false positive     | REDACT*        |
| 1.0         | Terms file entry — known term, not inferred  | REDACT         |

*All detections are written to the review file regardless of confidence. The
`--threshold` flag pre-sets low-confidence rows to `SKIP` while still including
them in the file, so the human can see them and override if needed.

**Tip:** Run `detect.py --threshold 0.85` to pre-skip low-confidence hits while
still seeing them in the review file for awareness. This reduces the number of
rows you need to manually change to `SKIP`.

---

## Setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# First run: the model (~2.8 GB) is downloaded automatically from HuggingFace
# and cached in ~/.cache/huggingface. Subsequent runs load from cache.
```

---

## Usage

### Step 1 — Detect

```bash
python detect.py --doc input/sample_document.xlsx
```

With a terms file and confidence threshold:

```bash
python detect.py \
  --doc input/sample_document.xlsx \
  --terms input/terms.txt \
  --threshold 0.85
```

On GPU:

```bash
python detect.py --doc input/report.xlsx --device cuda
```

Output: `output/<stem>_review.csv`

### Step 2 — Human Review

Open `output/sample_document_review.csv` in Excel, LibreOffice, or any CSV editor.

The review file is sorted **confidence ascending** — low-confidence rows appear
first because they need the most attention. High-confidence rows at the bottom
need the least review time.

For each row:
- Change `action` to `SKIP` to exclude a detection (false positive or out of scope)
- Edit `replacement` from the generic label (e.g. `[PRIVATE_PERSON]`) to a
  meaningful token (e.g. `[EMPLOYEE-A]`, `[CLIENT]`)
- Add rows for any PII the model missed — set `action=REDACT` and fill in `word`,
  `replacement`, and optionally `location` and `notes`
- Add reviewer comments in the `notes` column

Save the file.

### Step 3 — Redact

```bash
python redact.py \
  --doc input/sample_document.xlsx \
  --review output/sample_document_review.csv
```

With verbose substitution output:

```bash
python redact.py \
  --doc input/sample_document.xlsx \
  --review output/sample_document_review.csv \
  --verbose
```

Custom output path:

```bash
python redact.py \
  --doc input/report.xlsx \
  --review output/report_review.csv \
  --output /secure/share/report_anon.xlsx
```

Output: `output/<stem>_redacted<ext>` + `output/<stem>_redacted.log.json`

---

## Supported File Formats

| Format       | Read | Write | Location format               |
|--------------|------|-------|-------------------------------|
| `.txt` `.md` | ✓    | ✓     | `Line N`                      |
| `.docx`      | ✓    | ✓     | `Para N`                      |
| `.xlsx`      | ✓    | ✓     | `SheetName!ColRow` (e.g. `Contacts!B4`) |
| `.csv`       | ✓    | ✓     | `Row N, Col M`                |
| `.pdf`       | ✓    | ✗ *   | `Page N, Line M`              |
| `.pptx`      | ✓    | ✓     | `Slide N / Shape: <name>`     |

*PDF read-back is not supported. `redact.py` writes a `.txt` file with a header note.

---

## Using the Terms File

The terms file lets you inject **known, organisation-specific terms** that the
model may not reliably detect — internal codenames, server hostnames, client
names, project aliases.

Format: two columns, no header, one term per line:

```
Acme Corporation,[CLIENT]
Project Falcon,[PROJECT]
TIGERS,[SYSTEM]
PROD-DB-01,[SERVER-PROD]
```

Left column: word/phrase to find (case-insensitive, regex-escaped).
Right column: exact replacement token.

Terms file entries bypass the model. They are added to the review file with
`confidence=1.0` and `action=REDACT` so the human can still override them if
a particular occurrence should not be redacted.

Pass the terms file to `detect.py`:

```bash
python detect.py --doc input/report.xlsx --terms input/terms.txt
```

---

## Review File Format

Columns in `output/<stem>_review.csv`:

| Column        | Description |
|---------------|-------------|
| `word`        | The detected text as it appears in the document |
| `label`       | PII category: `PRIVATE_PERSON`, `PRIVATE_EMAIL`, `PRIVATE_PHONE`, `PRIVATE_URL`, `PRIVATE_DATE`, `PRIVATE_ADDRESS`, `ACCOUNT_NUMBER`, `SECRET`, `PRIVATE_TERM` |
| `confidence`  | Float 0.0–1.0. `1.0` for terms-file entries. |
| `action`      | `REDACT` or `SKIP` — **this is the column you edit** |
| `replacement` | Token to substitute. Pre-populated as `[LABEL]`. Edit to something meaningful. |
| `location`    | Where in the document (e.g. `Contacts!B4`, `Para 12`, `Line 47`) |
| `notes`       | Free-text column for reviewer comments. Not used by `redact.py`. |

The file is sorted **confidence ascending** (lowest first). Rows with `action=SKIP`
are written to the audit log under `skipped` but never applied to the document.

---

## Audit Log

`redact.py` writes `output/<stem>_redacted.log.json` after every run:

```json
{
  "source_document": "/path/to/input/report.xlsx",
  "review_file": "/path/to/output/report_review.csv",
  "output_document": "/path/to/output/report_redacted.xlsx",
  "timestamp": "2026-04-27T09:45:00+00:00",
  "total_applied": 12,
  "total_skipped": 3,
  "redactions": [
    {
      "word": "Alice Johnson",
      "replacement": "[EMPLOYEE-A]",
      "label": "PRIVATE_PERSON",
      "confidence": 0.997,
      "location": "Contacts!A2",
      "occurrences": 4
    }
  ],
  "skipped": [
    {
      "word": "March",
      "label": "PRIVATE_DATE",
      "confidence": 0.612,
      "reason": "action=SKIP"
    }
  ]
}
```

`occurrences` is the count of times the word appeared in the **original** document
(across all occurrences, not just the one the model flagged).

---

## End-to-End Example

```bash
# 1. Detect PII
python detect.py \
  --doc input/sample_document.xlsx \
  --terms input/terms.txt \
  --threshold 0.85

# 2. Review output/sample_document_review.csv in your editor
#    - Change action=SKIP on false positives
#    - Edit replacements: [PRIVATE_PERSON] → [EMPLOYEE-A] etc.
#    - Add any rows the model missed

# 3. Redact
python redact.py \
  --doc input/sample_document.xlsx \
  --review output/sample_document_review.csv \
  --verbose

# Check output/sample_document_redacted.xlsx
# Check output/sample_document_redacted.log.json
```

---

## Known Limitations

- **PDF write-back**: `pdfplumber` can extract text but cannot write back to PDF
  structure. Redacted PDFs are written as `.txt` with a header note.
- **Model recall**: `openai/privacy-filter` is a general-purpose filter. It may
  miss domain-specific identifiers (internal codenames, account formats, custom
  tokens). Use `--terms` to supplement.
- **Short cell values**: single words or two-word cells in xlsx/csv may produce
  lower confidence scores than the same text in a longer sentence — the model
  uses surrounding context. This is expected behaviour; review low-confidence hits
  carefully.
- **Run-spanning text in docx/pptx**: Word and PowerPoint sometimes split a single
  word across multiple internal "runs" (e.g. when formatting changes mid-word).
  The writer reconstructs text at the paragraph level, which preserves paragraph
  formatting but may flatten character-level formatting within affected paragraphs.
- **Not a compliance certification**: This tool is an aid for document review, not
  a certified compliance mechanism. Always have a human review the output before
  distribution.

---

## Project Structure

```
doc-anonymizer-v2/
├── detect.py              # Phase 1 CLI
├── redact.py              # Phase 2 CLI
├── requirements.txt
├── README.md
├── core/
│   ├── privacy_filter.py  # Singleton wrapper for openai/privacy-filter
│   ├── doc_reader.py      # Format-aware reader → chunks with location metadata
│   ├── doc_writer.py      # Format-aware writer applying substitutions
│   └── review_file.py     # CSV read/write for the human-review file
├── input/
│   ├── sample_document.txt
│   ├── sample_document.xlsx
│   └── terms.txt
└── output/                # Generated files land here
```
