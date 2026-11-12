"""Score extraction against hand-labelled gold files (eval/gold/<bill_id>.json).
Rules follow the task: text and dates must match exactly, numbers within +-1."""
import json
from pathlib import Path

from . import extract, pipeline

NUM_TOL = 1.0
LIST_FIELDS = ("charges", "taxes")


def _num_ok(p, g) -> bool:
    if g is None or p is None:
        return g is None and p is None
    return isinstance(p, (int, float)) and abs(p - g) <= NUM_TOL


def _list_score(pred: list[dict], gold: list[dict]) -> float:
    """Fraction of items matched by (type, amount within tolerance), penalising extras."""
    if not gold and not pred:
        return 1.0
    unused = list(pred)
    hit = 0
    for g in gold:
        for p in unused:
            if p["type"] == g["type"] and _num_ok(p["amount"], g["amount"]):
                unused.remove(p)
                hit += 1
                break
    return hit / max(len(gold), len(pred))


def score_bill(pred: dict, gold: dict) -> tuple[float, dict[str, float]]:
    per: dict[str, float] = {}
    for k, g in gold.items():
        p = pred.get(k)
        if k in LIST_FIELDS:
            per[k] = _list_score(p or [], g)
        elif isinstance(g, (int, float)) or g is None and isinstance(p, (int, float)):
            per[k] = 1.0 if _num_ok(p, g) else 0.0
        else:
            per[k] = 1.0 if p == g else 0.0
    return sum(per.values()) / len(per), per


def run_eval(bills_dir: Path, gold_dir: Path, model: str | None = None, use_fewshot: bool = True) -> dict:
    results, totals = {}, []
    for gp in sorted(Path(gold_dir).glob("*.json")):
        if gp.name.endswith(".draft.json"):
            continue
        bill_id = gp.stem
        gold = json.loads(gp.read_text(encoding="utf-8"))
        ext, warnings = pipeline.decode_one(extract.find_image(bills_dir, bill_id), model, True, use_fewshot)
        total, per = score_bill(ext.to_level1(), gold)
        results[bill_id] = {"score": round(total, 4), "wrong_fields": sorted(k for k, v in per.items() if v < 1),
                            "warnings": warnings}
        totals.append(total)
    summary = {"bills": len(totals), "mean_field_accuracy": round(sum(totals) / len(totals), 4) if totals else None,
               "per_bill": results}
    return summary
