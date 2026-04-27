# Doc Anonymizer v2 — Two-Stage PII Redaction Pipeline

A local, offline-capable CLI tool that redacts Personally Identifiable Information (PII) from documents using a two-stage pipeline:

1. **Stage 1 — Pattern Matcher**: Fast regex-based replacement of known org-specific terms (names, project codes, hostnames, etc.) from a user-supplied word list.
2. **Stage 2 — OpenAI Privacy Filter**: Context-aware PII detection using the [`openai/privacy-filter`](https://huggingface.co/openai/privacy-filter) model via HuggingFace Transformers — catches names, emails, phone numbers, SSNs, and other PII that the word list missed.

**All processing runs locally. No data leaves the machine.**

---

## Why Two Stages?

| | Stage 1 | Stage 2 |
|---|---|---|
| **Strength** | Zero false-negatives for known terms; instant | Context-aware; catches unknown PII |
| **Weakness** | Only finds what you list | Needs surrounding context; may miss single words |
| **Best for** | Project codes, hostnames, org names | Names, emails, phone numbers, SSNs |

The two stages are complementary: Stage 1 provides deterministic recall for org-specific secrets; Stage 2 provides probabilistic coverage for general PII.

---

## Setup

```bash
# 1. Navigate to this directory
cd Simple-Doc-Anonymizer

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> **First run note**: Stage 2 downloads the `openai/privacy-filter` model (~2.8 GB) from HuggingFace on the first invocation. After that it is cached at `~/.cache/huggingface/hub/`. Subsequent runs are instant.

---

## Usage

```
python3 anonymize.py --doc <path> [--terms <path>] [--output <path>]
                     [--pattern-only] [--no-pattern] [--verbose]
                     [--device cpu|cuda]
```

### Flags

| Flag | Description |
|---|---|
| `--doc` | **Required.** Path to the input document |
| `--terms` | Optional. Path to a terms file (one term per line). If omitted, Stage 1 is skipped |
| `--output` | Optional. Defaults to `output/<stem>_redacted<ext>` |
| `--pattern-only` | Skip Stage 2 (no model download required) |
| `--no-pattern` | Skip Stage 1 |
| `--verbose` | Print full redaction log to console |
| `--device` | `cpu` (default) or `cuda` |

---

## Usage Examples

### Plain text document
```bash
python3 anonymize.py --doc input/sample_document.txt --terms input/terms.txt
```

### Excel spreadsheet (cell-by-cell, structure preserved)
```bash
python3 anonymize.py --doc input/sample_document.xlsx --terms input/terms.txt
```

### CSV file
```bash
python3 anonymize.py --doc data/employees.csv --terms input/terms.txt
```

### Word document (.docx)
```bash
python3 anonymize.py --doc report.docx --terms input/terms.txt --verbose
```

### PowerPoint presentation (.pptx)
```bash
python3 anonymize.py --doc slides.pptx --terms input/terms.txt
```

### PDF (extracted text → .txt output)
```bash
python3 anonymize.py --doc contract.pdf --terms input/terms.txt
# Output is written as contract_redacted.txt (PDF write-back not supported)
```

### Pattern match only (no model download)
```bash
python3 anonymize.py --doc data.xlsx --terms input/terms.txt --pattern-only
```

### Privacy filter only (no word list)
```bash
python3 anonymize.py --doc report.docx --no-pattern --device cuda
```

### Custom output path
```bash
python3 anonymize.py --doc input/report.xlsx --terms input/terms.txt \
                     --output /secure/output/report_clean.xlsx
```

---

## Terms File Format

`input/terms.txt` — one term per line. Lines starting with `#` are comments:

```
# Internal project names
Project Falcon
TIGERS

# Infrastructure
PROD-DB-01

# Org names
Acme Corporation
```

Terms are matched case-insensitively and sorted longest-first to avoid partial replacements (e.g. "Project Falcon Team" is matched before "Project Falcon").

---

## Output

### Files produced

| File | Description |
|---|---|
| `output/<stem>_redacted<ext>` | Redacted document |
| `output/<stem>_redacted.log.json` | Redaction log (JSON sidecar) |

### Redaction markers

| Source | Marker | Meaning |
|---|---|---|
| Stage 1 | `[KNOWN_TERM]` | Matched an entry in your terms file |
| Stage 2 | `[PRIVATE_PERSON]`, `[SECRET]`, etc. | Model-detected PII label |

### Log schema

```json
{
  "source_document": "input/report.xlsx",
  "output_document": "output/report_redacted.xlsx",
  "timestamp": "2026-04-26T10:30:00.000000",
  "total_redactions": 70,
  "redactions": [
    {
      "source": "pattern",
      "term": "Project Falcon",
      "location": "sheet='Contacts' row=2 col=1"
    },
    {
      "source": "privacy_filter",
      "original": "john.smith@acme.com",
      "label": "PRIVATE_EMAIL",
      "score": 0.9987,
      "location": "paragraph 3"
    }
  ]
}
```

---

## Supported Formats

| Format | Read | Write | Notes |
|---|---|---|---|
| `.txt`, `.md` | ✅ | ✅ | Plain text |
| `.docx` | ✅ | ✅ | Paragraph structure preserved |
| `.xlsx`, `.xls` | ✅ | ✅ | Cell-by-cell; formatting, sheet names preserved |
| `.csv` | ✅ | ✅ | Headers and structure preserved |
| `.pdf` | ✅ (extract) | ⚠️ as `.txt` | PDF write-back not supported |
| `.pptx` | ✅ | ✅ | All slides and shapes processed |

---

## Known Limitations

1. **PDF write-back not supported.** PDF output is extracted text saved as `.txt`. Formatting, images, and layout are lost.

2. **~96% recall, not 100%.** The `openai/privacy-filter` model has a documented recall of approximately 96% on its benchmark. It is **not a compliance tool**. Use it as a first-pass filter; a human review is still recommended for sensitive documents.

3. **Short cells / single words.** The privacy filter needs surrounding context to identify PII. Isolated single-word cells (e.g., a cell containing just "Smith") may not be flagged. The Stage 1 pattern matcher is the primary defence for these cases.

4. **First run downloads ~2.8 GB.** The model is cached after the first download at `~/.cache/huggingface/hub/`.

5. **Non-English text.** The model was trained primarily on English text. Performance on other languages is not guaranteed.

6. **Excel read-back compatibility.** `.xls` (old binary format) is read via `openpyxl` in compatibility mode; the output is always `.xlsx`.

---

## Project Structure

```
Simple-Doc-Anonymizer/
├── anonymize.py              # CLI entry point
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py
│   ├── pattern_matcher.py    # Stage 1 — regex term replacement
│   ├── privacy_filter.py     # Stage 2 — HuggingFace token classification
│   ├── doc_reader.py         # Format-aware reader
│   └── doc_writer.py         # Format-aware writer
├── input/
│   ├── sample_document.txt   # Sample meeting notes with PII
│   ├── sample_document.xlsx  # Sample spreadsheet with PII
│   └── terms.txt             # Sample org-specific terms
└── output/                   # Redacted files land here

```
## 📜 License

MIT License. Use freely, modify, and share!

## Author

Erick Perales  — IT Architect, Cloud Migration Specialist
