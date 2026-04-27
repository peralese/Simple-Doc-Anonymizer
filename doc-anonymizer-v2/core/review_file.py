"""Read and write the human-review CSV for doc-anonymizer-v2."""

import csv
import sys
from pathlib import Path


COLUMNS = ["word", "label", "confidence", "action", "replacement", "location", "notes"]
VALID_ACTIONS = {"REDACT", "SKIP"}


def write_review_csv(detections: list[dict], output_path: str) -> None:
    """
    Write detections to a review CSV.
    Sorted confidence-ascending so low-confidence rows appear first
    — those need the most human attention.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(detections, key=lambda d: float(d.get("confidence", 0.0)))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})


def read_review_csv(path: str) -> list[dict]:
    """
    Read and validate the review CSV.
    Warns on unrecognised action values and skips those rows.
    Returns a list of validated row dicts.
    """
    rows: list[dict] = []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for csv_row_num, row in enumerate(reader, start=2):  # row 1 is header
            raw_action = row.get("action", "")
            action = raw_action.strip().upper()

            if action not in VALID_ACTIONS:
                print(
                    f"  Warning: row {csv_row_num} has unrecognised action {raw_action!r} "
                    f"(word={row.get('word')!r}) — skipping",
                    file=sys.stderr,
                )
                continue

            try:
                confidence = float(row.get("confidence", 0.0))
            except ValueError:
                confidence = 0.0

            rows.append({
                "word":        row.get("word", "").strip(),
                "label":       row.get("label", "").strip(),
                "confidence":  confidence,
                "action":      action,
                "replacement": row.get("replacement", "").strip(),
                "location":    row.get("location", "").strip(),
                "notes":       row.get("notes", "").strip(),
            })

    return rows
