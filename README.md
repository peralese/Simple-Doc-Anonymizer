# Word Document Anonymizer

A simple Python utility to anonymize Microsoft Word (.docx) documents by replacing sensitive terms with placeholders. Supports multiple substitutions in one run and generates a CSV log to track (and potentially revert) changes.

---

## Features

- Interactive prompts for:
  - Word file path
  - Multiple original → replacement term pairs
- Replaces text in:
  - Paragraphs
  - Tables
- Tracks number of replacements per term
- Saves:
  - New anonymized `.docx` file
  - CSV substitution log
- CSV log can be used to *revert* changes later

---

## Example Use Case

You have a document mentioning:

- “ACME Corp”
- “ACME”
- “ACME Corporation”

You want to replace all with:

```
<client>
```

After running, the script:

- Anonymizes the document
- Creates a CSV log like:

| original_term      | replacement_term | occurrences |
|---------------------|------------------|-------------|
| ACME Corp           | <client>         | 3           |
| ACME                | <client>         | 2           |
| ACME Corporation    | <client>         | 1           |

---

## Requirements

- Python 3.7 or higher
- `python-docx` library

Install the dependency with:

```bash
pip install python-docx
```

---

## How to Use

1. Save the script to a file, e.g. `anonymize_docx.py`.

2. Open your terminal or command prompt.

3. Run the script:

```bash
python anonymize_docx.py
```

4. Follow the interactive prompts:

- Enter the full path to your `.docx` file.
- Add one or more original → replacement pairs.
- Leave blank when finished entering substitutions.

---

## Example Interactive Session

```
$ python anonymize_docx.py

=== Word Document Anonymizer ===
Enter the full path to the .docx file: /Users/me/Documents/report.docx

Enter substitution pairs (original -> replacement).
Enter original term (or leave blank to finish): ACME Corp
Enter replacement for 'ACME Corp': <client>
Enter original term (or leave blank to finish): ACME
Enter replacement for 'ACME': <client>
Enter original term (or leave blank to finish): ACME Corporation
Enter replacement for 'ACME Corporation': <client>
Enter original term (or leave blank to finish):

Loading document...

=== Anonymization Complete ===
Anonymized document saved to: /Users/me/Documents/report_anonymized.docx
Substitution log saved to: /Users/me/Documents/report_substitution_log.csv

Summary of replacements:
  'ACME Corp' -> '<client>': 3 occurrence(s)
  'ACME' -> '<client>': 2 occurrence(s)
  'ACME Corporation' -> '<client>': 1 occurrence(s)
```

---

## Outputs

- **Anonymized DOCX file**
  - Same folder as original
  - Named like `report_anonymized.docx`
- **CSV substitution log**
  - Same folder as original
  - Named like `report_substitution_log.csv`

Example CSV content:

```
original_term,replacement_term,occurrences
ACME Corp,<client>,3
ACME,<client>,2
ACME Corporation,<client>,1
```

---

## Notes

- Processes text in:
  - Paragraphs
  - Table cells
- Does *not yet* handle:
  - Headers
  - Footers
  - Text boxes
  - Comments
- CSV log makes *future reversal* straightforward.

---

## Suggested Improvements

- Add header/footer support
- CLI argument mode (no interactive prompts)
- Batch substitutions via pre-defined CSV
- Reversion script to undo changes using the CSV log
- GUI version

---

## License

MIT License. Use freely, modify, and share!

## Author

Erick Perales  — IT Architect, Cloud Migration Specialist