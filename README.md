# Doc Anonymizer v2

A two-phase, human-in-the-loop document anonymization pipeline powered by the
[openai/privacy-filter](https://huggingface.co/openai/privacy-filter) model from
HuggingFace, with a post-processing span merger to eliminate token fragmentation.

---

## Philosophy: Why Human-in-the-Loop?

The OpenAI Privacy Filter is a **detector**, not a redactor. It returns detected PII
spans with confidence scores. No automated system is perfect:

- **False positives** (over-redaction) can make a document meaningless
- **False negatives** (missed PII) can expose sensitive information

Both failure modes have real consequences. This tool deliberately separates detection
from redaction with a human review step between them. The human confirms hits, rejects
false positives, edits replacement tokens to meaningful values, and adds anything the
model missed — then `redact.py` runs. The human's decisions are authoritative;
`redact.py` never re-runs the model.

---

## The Token Fragmentation Problem

### Root Cause

The Privacy Filter is a transformer token classifier. Text is broken into subword tokens
before classification, and punctuation characters (`. @ - _ space`) create token
boundaries that can prevent the aggregation strategy from merging what should be a
single PII span. This produces **fragment rows** in the review file:

| What you'd expect | What `aggregation_strategy="simple"` can produce |
|-------------------|--------------------------------------------------|
| `bob.martinez@acme.com` (1 row) | `bob.martinez@acme` + `.com` (2 rows) |
| `(555) 345-6789` (1 row) | `(555) 345-678` + `9` (2 rows) |
| `Bob Martinez` (1 row) | `Bob` + `Martinez` (2 rows) |
| `sk-a1b2c3d4` (1 row) | `sk` + `-a1b2c3d4` (2 rows) |

Fragments reaching the human reviewer require manual merging and create confusion.

### Fix 1 — `aggregation_strategy="max"`

`core/privacy_filter.py` uses `aggregation_strategy="max"` when building the HuggingFace
pipeline. Comparison of strategies:

| Strategy | Merging behaviour | Score |
|----------|-------------------|-------|
| `none`   | No merging — raw tokens | Per token |
| `simple` | Merges consecutive same-label tokens, **splits at punctuation** | Average |
| `max`    | Merges consecutive same-label spans, **handles punctuation boundaries** | Highest token score ✓ |
| `first`  | Merges spans | First token score |

`max` is the correct choice: it merges the full span across punctuation and reports the
most conservative (highest) confidence score, so a genuine PII detection is never
under-reported.

### Fix 2 — Post-Processing Span Merger (`core/span_merger.py`)

Even with `aggregation_strategy="max"`, edge cases can still produce fragments —
particularly across punctuation in emails, phone formatting characters, and hyphenated
names. `core/span_merger.merge_adjacent_spans()` is a second line of defence:

```
merge_adjacent_spans(detections, original_text, gap_tolerance=2)
```

**Algorithm:**
1. Sort detections by start character position (ascending)
2. For each detection, check if the next detection has the **same label** and a start
   position within `gap_tolerance` characters of the current end position:
   `next.start − current.end ≤ gap_tolerance`
3. If both conditions hold → **merge**: combined word = `original_text[current.start : next.end]`,
   combined confidence = `max(a.confidence, b.confidence)`
4. Otherwise → emit current span and advance

`gap_tolerance=2` (default) handles single punctuation characters and space+punctuation
combinations. Set `--gap-tolerance 0` to disable gap bridging if you see over-merging.

**Call order in detect.py:**
```
raw   = privacy_filter.detect(chunk_text)          # pipeline with max strategy
merged = span_merger.merge_adjacent_spans(          # post-process
    raw, chunk_text, gap_tolerance=2
)
# then global safety pass, then write review CSV
```

The console output shows you exactly how much work the merger did:
```
Raw detections : 31
After merging  : 18  (13 fragments consolidated)
```

---

## Understanding Confidence Scores

| Range       | Meaning                                                   | Default action |
|-------------|-----------------------------------------------------------|----------------|
| ≥ 0.95      | High confidence — likely PII                              | REDACT         |
| 0.70 – 0.94 | Medium confidence — review carefully                      | REDACT         |
| < 0.70      | Low confidence — probable false positive                  | REDACT*        |
| 1.0         | Terms file entry — known term, not inferred               | REDACT         |

*All detections are written to the review file regardless of confidence. The
`--threshold` flag pre-sets low-confidence rows to `SKIP` while still including them in
the file so the human can see and override them.

**Tip:** Run `detect.py --threshold 0.85` to pre-flag low-confidence hits as SKIP while
keeping them visible for awareness.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **First run:** the model (~2.8 GB) downloads automatically from HuggingFace and is
> cached at `~/.cache/huggingface/hub/`. All subsequent runs load from disk — no
> network call. `redact.py` never loads the model at all.

---

## Usage

### Phase 1 — Detect

```bash
python detect.py --doc input/sample_document.txt
```

With a terms file and confidence threshold:

```bash
python detect.py \
  --doc input/sample_document.xlsx \
  --terms input/terms.txt \
  --threshold 0.85
```

On GPU, disabling span bridging:

```bash
python detect.py --doc input/report.docx --device cuda --gap-tolerance 0
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--doc` | required | Input document path |
| `--terms` | — | Supplemental terms file (term,replacement per line) |
| `--threshold` | `0.0` | Confidence threshold; detections below → action=SKIP |
| `--device` | `cpu` | `cpu` or `cuda` |
| `--gap-tolerance` | `2` | Character gap for span merger. `0` disables bridging |

Output: `output/<stem>_review.csv`

### Phase 2 — Human Review

Open `output/<stem>_review.csv` in Excel, LibreOffice, or any CSV editor.

The file is sorted **confidence ascending** — low-confidence rows appear first because
they need the most attention. High-confidence rows at the bottom need the least review.

For each row:
- Change `action` to `SKIP` to exclude (false positive or out of scope)
- Edit `replacement` from the generic label (`[PRIVATE_PERSON]`) to something meaningful
  (`[EMPLOYEE-A]`, `[CLIENT]`, `[VENDOR]`)
- Add rows for any PII the model missed — set `action=REDACT` with `word` and
  `replacement` filled in
- Add reviewer comments in `notes` (ignored by `redact.py`)

### Phase 3 — Redact

```bash
python redact.py \
  --doc input/sample_document.xlsx \
  --review output/sample_document_review.csv
```

With verbose output:

```bash
python redact.py \
  --doc input/sample_document.txt \
  --review output/sample_document_review.csv \
  --verbose
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--doc` | Required. Original document (same file used in detect.py) |
| `--review` | Required. Human-edited review CSV |
| `--output` | Optional. Defaults to `output/<stem>_redacted<ext>` |
| `--verbose` | Print each substitution as it is applied |

Output: `output/<stem>_redacted<ext>` + `output/<stem>_redacted.log.json`

---

## Supported File Formats

| Format | Read | Write | Location format |
|--------|------|-------|-----------------|
| `.txt` `.md` | ✓ | ✓ | `Line N` |
| `.docx` | ✓ | ✓ | `Para N` |
| `.xlsx` | ✓ | ✓ | `SheetName!ColRow` e.g. `Contacts!B4` |
| `.csv` | ✓ | ✓ | `Row N, Col M` |
| `.pdf` | ✓ | ✗ * | `Page N, Line M` |
| `.pptx` | ✓ | ✓ | `Slide N / Shape: <name>` |

*PDF write-back not supported. `redact.py` writes a `.txt` file with a header note.

For xlsx, detection and redaction happen **cell by cell** — location strings like
`Contacts!B4` are meaningful to the human reviewer.

---

## Terms File

`input/terms.txt` — known org-specific terms the model may miss (codenames, server
names, client names, internal product names).

**Format:** two columns, no header, one term per line:

```
Acme Corporation,[CLIENT]
Project Falcon,[PROJECT]
TIGERS,[SYSTEM]
eReporting,[SYSTEM]
PROD-DB-01,[SERVER-PROD]
```

Left column: text to find (case-insensitive, regex-escaped).  
Right column: exact replacement token.

Terms bypass the model. They appear in the review file with `confidence=1.0` and
`action=REDACT` so the human can still override them if a particular occurrence should
not be redacted.

---

## Review File Format

Columns in `output/<stem>_review.csv`:

| Column | Description |
|--------|-------------|
| `word` | The detected text exactly as it appears in the document |
| `label` | PII category: `PRIVATE_PERSON`, `PRIVATE_EMAIL`, `PRIVATE_PHONE`, `PRIVATE_URL`, `PRIVATE_DATE`, `PRIVATE_ADDRESS`, `ACCOUNT_NUMBER`, `SECRET`, `PRIVATE_TERM` |
| `confidence` | 0.0 – 1.0. `1.0` for terms-file entries. |
| `action` | **Edit this.** `REDACT` to apply, `SKIP` to exclude |
| `replacement` | **Edit this.** Pre-populated as `[LABEL]`. Change to a meaningful token. |
| `location` | Where in the document — read-only reference |
| `notes` | Free-text for reviewer comments — not used by `redact.py` |

Rows are sorted **confidence ascending** so uncertain rows appear first.

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
      "word": "Bob Martinez",
      "replacement": "[EMPLOYEE-B]",
      "label": "PRIVATE_PERSON",
      "confidence": 0.998,
      "location": "Contacts!A2",
      "occurrences": 3
    }
  ],
  "skipped": [
    { "word": "March 15", "label": "PRIVATE_DATE", "confidence": 0.612, "reason": "action=SKIP" }
  ]
}
```

`occurrences` is the count of times the word appeared in the **original** document.

---

## Unit Tests

```bash
python test_span_merger.py
```

Covers 11 cases: person name space gap, email dot fragmentation, phone number
fragmentation, secret key hyphen fragmentation, different labels not merged, same-label
far-apart spans not merged, empty input, single detection passthrough, zero gap
tolerance disables bridging, three-way merge, and unsorted input.

---

## Project Structure

```
doc-anonymizer-v2/
├── detect.py                 # Phase 1 CLI
├── redact.py                 # Phase 2 CLI
├── test_span_merger.py       # Unit tests for span merger
├── requirements.txt
├── README.md
├── core/
│   ├── privacy_filter.py     # Singleton model wrapper (aggregation_strategy="max")
│   ├── span_merger.py        # Post-processing span merger
│   ├── doc_reader.py         # Format-aware reader → chunks with location metadata
│   ├── doc_writer.py         # Format-aware writer applying substitutions
│   └── review_file.py        # CSV read/write for the human-review file
├── input/
│   ├── sample_document.txt   # Meeting notes exercising all PII categories
│   ├── sample_document.xlsx  # Spreadsheet with emails/phones for merger testing
│   └── terms.txt             # Org-specific terms (two-column format)
└── output/
```

---

## Known Limitations

- **PDF write-back not supported.** `redact.py` writes redacted content as `.txt`.
- **~96% model recall.** `openai/privacy-filter` is not a compliance tool. The human
  review step exists to catch the remaining ~4% and context-specific misses.
- **Short cell values.** Single-word or two-word cells may produce lower confidence
  scores — the model benefits from surrounding context. Use the terms file for known
  short-form identifiers.
- **First run downloads ~2.8 GB.** Cached at `~/.cache/huggingface/hub/` afterwards.
- **Non-English text.** The model was trained primarily on English.
- **Over-merging.** If the span merger is joining spans that should stay separate, use
  `--gap-tolerance 0` to disable gap bridging (only truly adjacent spans will merge).

---

## Author

Erick Perales — IT Architect, Cloud Migration Specialist
