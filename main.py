import csv
import os
from docx import Document

def get_substitution_map():
    substitutions = []
    print("\nEnter substitution pairs (original -> replacement).")
    while True:
        original = input("Enter original term (or leave blank to finish): ").strip()
        if not original:
            break
        replacement = input(f"Enter replacement for '{original}': ").strip()
        substitutions.append((original, replacement))
    return substitutions

def process_text(text, substitutions, stats):
    for original, replacement in substitutions:
        count = text.count(original)
        if count > 0:
            text = text.replace(original, replacement)
            stats[original]['count'] += count
    return text

def anonymize_docx():
    print("=== Word Document Anonymizer ===")

    # 1. Get file path
    file_path = input("Enter the full path to the .docx file: ").strip()
    if not os.path.isfile(file_path):
        print("Error: File not found.")
        return

    # 2. Get multiple substitutions
    substitutions = get_substitution_map()
    if not substitutions:
        print("No substitutions provided. Exiting.")
        return

    # 3. Initialize tracking
    stats = {orig: {'replacement': repl, 'count': 0} for orig, repl in substitutions}

    # 4. Load document
    print("\nLoading document...")
    doc = Document(file_path)

    # 5. Process paragraphs
    for para in doc.paragraphs:
        para.text = process_text(para.text, substitutions, stats)

    # 6. Process tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                cell.text = process_text(cell.text, substitutions, stats)

    # 7. Save new file
    dir_name, base_name = os.path.split(file_path)
    name, ext = os.path.splitext(base_name)
    new_file_path = os.path.join(dir_name, f"{name}_anonymized{ext}")
    doc.save(new_file_path)

    # 8. Save CSV mapping
    csv_file_path = os.path.join(dir_name, f"{name}_substitution_log.csv")
    with open(csv_file_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['original_term', 'replacement_term', 'occurrences'])
        for original in stats:
            writer.writerow([original, stats[original]['replacement'], stats[original]['count']])

    print("\n=== Anonymization Complete ===")
    print(f"Anonymized document saved to: {new_file_path}")
    print(f"Substitution log saved to: {csv_file_path}")
    print("\nSummary of replacements:")
    for original in stats:
        print(f"  '{original}' -> '{stats[original]['replacement']}': {stats[original]['count']} occurrence(s)")

if __name__ == "__main__":
    anonymize_docx()
