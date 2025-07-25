# Word Document Anonymizer

A Python utility to anonymize Microsoft Word (.docx) files by replacing sensitive terms with placeholders. Supports both interactive and CSV-driven workflows, tracks all substitutions, and saves a log file for possible reversal.

---

## ✅ Features

- Replace multiple terms in one run
- Option to input terms manually **or** load from CSV
- Replaces in:
  - Document body
  - Tables
  - **Headers**
  - **Footers**
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
- [`python-docx`](https://pypi.org/project/python-docx/)

Install via:

```bash
pip install python-docx
```

---

## 🚀 How to Run

```bash
python anonymize_docx.py
```

Follow the prompts:
- Enter the file path to your `.docx` file
- Choose input method: interactive or CSV
- Substitutions are processed and tracked

---

## 📄 Example Session

```
$ python anonymize_docx.py

=== Word Document Anonymizer ===
Enter the full path to the .docx file: /Users/me/Documents/report.docx
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

## 📦 Outputs

- **Anonymized DOCX File**  
  Saved in the same folder as input, named like `report_anonymized.docx`

- **CSV Log File**  
  Tracks each substitution and count, e.g.:

```csv
original_term,replacement_term,occurrences
ACME Corp,<client>,3
John Smith,<person>,2
```

---

## ⚠️ Notes

- Supports replacement in:
  - Paragraphs
  - Tables
  - Headers
  - Footers
- Does **not yet** support:
  - Text boxes or drawing shapes
  - Comments or revisions
  - Regex/case-insensitive matching
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