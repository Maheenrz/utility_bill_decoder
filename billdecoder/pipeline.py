"""Glue: templates in, completed CSVs + a review report out. Resumable (cached per bill)."""
import json
import logging
from pathlib import Path

from . import answer, config, csv_io, extract
from .analytics import build_facts
from .schema import Extraction

log = logging.getLogger("billdecoder")


class PipelineError(RuntimeError):
    pass


def _cache_path(kind: str, key: str) -> Path:
    d = config.CACHE_DIR / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def decode_one(image_path: Path, model: str | None = None, use_cache: bool = True,
               use_fewshot: bool = True) -> tuple[Extraction, list[str]]:
    """Image -> (Extraction, warnings). Used by the CLI and by the Streamlit app."""
    model = model or config.MODEL_NAME
    cp = _cache_path("extract", extract.cache_key(image_path, model, use_fewshot))
    if use_cache and cp.is_file():
        d = json.loads(cp.read_text(encoding="utf-8"))
        return Extraction.model_validate(d["extraction"]), d["warnings"]
    ext, warnings = extract.extract_bill(image_path, model, use_fewshot)
    cp.write_text(json.dumps({"extraction": ext.model_dump(mode="json"), "warnings": warnings}, indent=2),
                  encoding="utf-8")
    return ext, warnings


def answer_one(ext: Extraction, questions: list[dict], model: str | None = None,
               use_cache: bool = True) -> tuple[dict, dict[str, str]]:
    """(facts, {question_id: answer}) for one bill."""
    import hashlib
    model = model or config.MODEL_NAME
    facts = build_facts(ext)
    key = hashlib.sha256(json.dumps([ext.model_dump(mode="json"), questions, model, answer.PROMPT_VERSION,
                                     answer.PROMPT], sort_keys=True).encode()).hexdigest()[:20]
    cp = _cache_path("answers", key)
    if use_cache and cp.is_file():
        return facts, json.loads(cp.read_text(encoding="utf-8"))
    answers = answer.answer_questions(ext, facts, questions, model)
    cp.write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
    return facts, answers


def run_decode(bills_dir: Path, l1_template: Path, l2_template: Path, out_dir: Path,
               model: str | None = None, use_cache: bool = True, use_fewshot: bool = True) -> dict:
    out_dir = Path(out_dir)
    t1 = csv_io.read_template(l1_template, csv_io.L1_HEADERS)
    t2 = csv_io.read_template(l2_template, csv_io.L2_HEADERS)
    bill_ids = [r["bill_id"].strip() for r in t1]
    if len(bill_ids) != len(set(bill_ids)):
        raise PipelineError("level1 template has duplicate bill_ids")

    questions: dict[str, list[dict]] = {}
    for r in t2:
        questions.setdefault(r["bill_id"], []).append({"question_id": r["question_id"], "question": r["question"]})

    level1: dict[str, dict] = {}
    answers: dict[str, dict] = {}
    report: dict[str, dict] = {}
    failed: list[str] = []
    (out_dir / "facts").mkdir(parents=True, exist_ok=True)

    for i, bill_id in enumerate(bill_ids, start=1):
        try:
            log.info("[%d/%d] %s", i, len(bill_ids), bill_id)
            img = extract.find_image(bills_dir, bill_id)
            ext, warnings = decode_one(img, model, use_cache, use_fewshot)
            facts, ans = answer_one(ext, questions.get(bill_id, []), model, use_cache)
            level1[bill_id] = ext.to_level1()
            answers[bill_id] = ans
            (out_dir / "facts" / f"{bill_id}.json").write_text(json.dumps(facts, indent=2, default=str), encoding="utf-8")
            report[bill_id] = {"status": "ok" if not warnings else "needs_review", "warnings": warnings}
        except Exception as exc:                       # one bad bill must not lose the others
            log.exception("%s failed", bill_id)
            report[bill_id] = {"status": "failed", "error": str(exc)}
            failed.append(bill_id)

    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if failed:
        raise PipelineError(f"{len(failed)} bill(s) failed: {failed}. Fix and re-run: finished bills are cached. "
                            f"See {out_dir / 'report.json'}.")

    csv_io.write_csv(out_dir / "level1.csv", csv_io.L1_HEADERS, csv_io.level1_rows(t1, level1))
    csv_io.write_csv(out_dir / "level2.csv", csv_io.L2_HEADERS, csv_io.level2_rows(t2, answers))
    csv_io.verify_output(out_dir / "level1.csv", csv_io.L1_HEADERS, t1, ["bill_id"])
    csv_io.verify_output(out_dir / "level2.csv", csv_io.L2_HEADERS, t2, ["bill_id", "question_id", "question"])
    return report
