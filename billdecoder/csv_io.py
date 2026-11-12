"""CSV helpers: read the templates, write results, and prove the output matches the template."""
import csv
import json
from pathlib import Path

L1_HEADERS = ["bill_id", "json"]
L2_HEADERS = ["bill_id", "question_id", "question", "answer"]


def read_template(path: Path, headers: list[str]) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"template not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != headers:
            raise ValueError(f"{path}: expected columns {headers}, got {reader.fieldnames}")
        return list(reader)


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def level1_rows(template: list[dict], by_id: dict[str, dict]) -> list[dict]:
    return [{"bill_id": r["bill_id"],
             "json": json.dumps(by_id[r["bill_id"]], ensure_ascii=False, separators=(",", ":"), allow_nan=False)}
            for r in template]


def level2_rows(template: list[dict], answers: dict[str, dict[str, str]]) -> list[dict]:
    return [{"bill_id": r["bill_id"], "question_id": r["question_id"], "question": r["question"],
             "answer": answers[r["bill_id"]][r["question_id"]]} for r in template]


def verify_output(path: Path, headers: list[str], template: list[dict], keys: list[str]) -> None:
    """Read the written file back: same row count, same ids/questions in the same order, no empty cells."""
    rows = read_template(path, headers)
    if len(rows) != len(template):
        raise ValueError(f"{path}: {len(rows)} rows, template has {len(template)}")
    for i, (out, tpl) in enumerate(zip(rows, template), start=2):
        if any(out[k] != tpl[k] for k in keys):
            raise ValueError(f"{path}: row {i} changed an id/question from the template")
        empty = [h for h in headers if not out[h].strip()]
        if empty:
            raise ValueError(f"{path}: row {i} has empty cell(s): {empty}")
    if headers == L1_HEADERS:
        for i, out in enumerate(rows, start=2):
            json.loads(out["json"])      # raises if any cell is not valid JSON
