"""Command line entry point.

  python run.py decode --bills test/bills --level1 test/csv/level1.csv --level2 test/csv/level2.csv --out output
  python run.py eval   --bills train/bills --gold eval/gold
  python run.py draft  --bills train/bills --bill-id KESC_0004
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from billdecoder import config, evaluate, extract, llm, pipeline


def main() -> int:
    p = argparse.ArgumentParser(description="WTQ Utility Bill Decoder")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("decode", help="fill level1.csv and level2.csv from a folder of bills")
    d.add_argument("--bills", required=True, type=Path)
    d.add_argument("--level1", required=True, type=Path, help="level1.csv template")
    d.add_argument("--level2", required=True, type=Path, help="level2.csv template")
    d.add_argument("--out", default=Path("output"), type=Path)
    d.add_argument("--no-cache", action="store_true")
    d.add_argument("--no-fewshot", action="store_true")

    e = sub.add_parser("eval", help="score extraction against hand-labelled gold files")
    e.add_argument("--bills", required=True, type=Path)
    e.add_argument("--gold", default=Path("eval/gold"), type=Path)
    e.add_argument("--no-fewshot", action="store_true")

    g = sub.add_parser("draft", help="write a draft gold file you then correct by hand")
    g.add_argument("--bills", required=True, type=Path)
    g.add_argument("--bill-id", required=True)
    g.add_argument("--gold", default=Path("eval/gold"), type=Path)

    for s in (d, e, g):
        s.add_argument("--model", default=config.MODEL_NAME)
        s.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        llm.ensure_ready()
        if a.cmd == "decode":
            report = pipeline.run_decode(a.bills, a.level1, a.level2, a.out, a.model,
                                         use_cache=not a.no_cache, use_fewshot=not a.no_fewshot)
            review = [b for b, r in report.items() if r["status"] == "needs_review"]
            print(f"Done. Wrote {a.out}/level1.csv and {a.out}/level2.csv")
            if review:
                print(f"Review these bills (consistency warnings): {review}  -> see {a.out}/report.json")
        elif a.cmd == "eval":
            res = evaluate.run_eval(a.bills, a.gold, a.model, use_fewshot=not a.no_fewshot)
            Path("eval").mkdir(exist_ok=True)
            Path("eval/results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(json.dumps(res, indent=2))
        elif a.cmd == "draft":
            ext, warns = pipeline.decode_one(extract.find_image(a.bills, a.bill_id), a.model)
            out = a.gold / f"{a.bill_id}.draft.json"
            a.gold.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(ext.to_level1(), indent=2), encoding="utf-8")
            print(f"Wrote {out}\nOpen the bill image, correct EVERY value, then rename to {a.bill_id}.json")
            if warns:
                print("Model warnings:", *warns, sep="\n - ")
    except (pipeline.PipelineError, llm.LLMError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())