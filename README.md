# Simple Document Anonymizer

A Python utility to anonymize documents by replacing sensitive terms with placeholders. Now supports `.docx`, `.txt`, and `.json`. Supports both interactive and CSV-driven workflows, tracks all substitutions, and saves a log file for possible reversal.

---

## ✅ Features

- Replace multiple terms in one run
- Option to input terms manually **or** load from CSV
- DOCX coverage:
  - Document body, tables, **headers**, **footers**
- TXT coverage: entire file content
- JSON coverage: all string values (optional: string keys)
- Matching modes: literal or regex; optional case-insensitive
- Tracks number of replacements for each term
- Outputs:
  - Anonymized `.docx` file
  - Substitution log `.csv` file

---

## 📁 Supported Input Methods

You can provide substitutions in two ways:

### 1. **Interactive Input**  
The script prompts you to enter each `original → replacement` pair manually.

### 2. **CSV File Input**  
You can also supply a CSV file:

#### CSV Format Example:

```csv
original,replacement
ACME Corp,<client>
John Smith,<person>
MyProject,<project>
```

The script will ask:
```
Do you have a CSV file with substitutions? (y/n):
```

---

## 💻 Requirements

- Python 3.7 or higher
- [`python-docx`](https://pypi.org/project/python-docx/) (for `.docx` files)

Install via:

```bash
pip install python-docx
```

---

## 🚀 How to Run

```bash
python main.py
```

Follow the prompts:
- Enter the file path to your `.docx` file
- Choose input method: interactive or CSV
- Substitutions are processed and tracked

---

## 📄 Example Session (DOCX)

```
$ python main.py

=== File Anonymizer (.docx, .txt, .json) ===
Enter the full path to the file: /Users/me/Documents/report.docx
Do you have a CSV file with substitutions? (y/n): y
Enter the path to the CSV file: /Users/me/Documents/substitutions.csv

Loading document...

=== Anonymization Complete ===
Anonymized document saved to: /Users/me/Documents/report_anonymized.docx
Substitution log saved to: /Users/me/Documents/report_substitution_log.csv

Summary of replacements:
  'ACME Corp' -> '<client>': 3 occurrence(s)
  'John Smith' -> '<person>': 2 occurrence(s)
```

---

## 📄 Example Session (TXT)

```
$ python main.py

=== File Anonymizer (.docx, .txt, .json) ===
Enter the full path to the file: /Users/me/Documents/notes.txt
Do you have a CSV file with substitutions? (y/n): n
Enter substitution pairs (original -> replacement).
Enter original term (or leave blank to finish): ACME
Enter replacement for 'ACME': <client>
Enter original term (or leave blank to finish): 

=== Anonymization Complete ===
Anonymized file saved to: /Users/me/Documents/notes_anonymized.txt
Substitution log saved to: /Users/me/Documents/notes_substitution_log.csv
```

## 📄 Example Session (JSON)

```
$ python main.py

=== File Anonymizer (.docx, .txt, .json) ===
Enter the full path to the file: /Users/me/data/sample.json
Do you have a CSV file with substitutions? (y/n): y
Enter the path to the CSV file: /Users/me/data/subs.csv
Also anonymize string keys in JSON? (y/n): n
Choose matching mode:
  1) literal (case-sensitive)
  2) literal (case-insensitive)
  3) regex (case-sensitive)
  4) regex (case-insensitive)
Enter 1, 2, 3, or 4: 2

=== Anonymization Complete ===
Anonymized file saved to: /Users/me/data/sample_anonymized.json
Substitution log saved to: /Users/me/data/sample_substitution_log.csv
```

## 📦 Outputs

- **Anonymized File**  
  Saved in the same folder as input, named like `report_anonymized.docx`, `notes_anonymized.txt`, or `sample_anonymized.json`.

- **CSV Log File**  
  Tracks each substitution and count, e.g.:

```csv
original_term,replacement_term,occurrences
ACME Corp,<client>,3
John Smith,<person>,2
```

---

## ⚠️ Notes

- DOCX supports replacement in: paragraphs, tables, headers, footers
- JSON anonymizes string values; string keys optional via prompt
- Does **not yet** support:
  - Text boxes or drawing shapes
  - Comments or revisions
  - Whole-word-only matching (can be approximated with regex, e.g., `\bterm\b`)

## 🔎 Matching Modes
- literal (case-sensitive): exact substring replacement (`"Acme"` != `"ACME"`).
- literal (case-insensitive): uses case-insensitive search, replaces with the provided replacement literal.
- regex (case-sensitive/insensitive): treats `original` as a regex pattern.
  - CSV input: `original` is interpreted as a regex when regex mode is selected.
  - Example whole-word email: `(?i)\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b`
  - Example whole-word client: `\bACME\b`
- These are planned future features (see below)

---

## 🛠️ Planned Enhancements

- ✅ Header/Footer support ✅ (*Implemented*)
- 🟡 Text box and shape support
- 🟡 Reversion script (undo anonymization using CSV log)
- 🟡 Logging and dry run mode
- 🟡 Case-insensitive and regex matching
- 🟡 GUI version or web front-end
- 🟡 CLI mode using `argparse`

---

## 📜 License

MIT License. Use freely, modify, and share!

## Author

Erick Perales  — IT Architect, Cloud Migration Specialist
