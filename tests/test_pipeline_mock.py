"""End-to-end run with the model mocked: proves the plumbing (templates -> CSVs, cache,
repair loop, failure handling) works without an API key."""
import json

import pytest
from PIL import Image

from billdecoder import config, csv_io, llm, pipeline
from billdecoder.schema import AnswerSet, Extraction
from tests.helpers import make_extraction


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(config, "FEWSHOT_BILL", tmp_path / "none.png")      # no few-shot in tests
    bills = tmp_path / "bills"
    bills.mkdir()
    for b in ("IESCO_0001", "KESC_0001"):
        Image.new("RGB", (50, 50), "white").save(bills / f"{b}.png")
    csv_io.write_csv(tmp_path / "l1.csv", csv_io.L1_HEADERS,
                     [{"bill_id": "IESCO_0001", "json": ""}, {"bill_id": "KESC_0001", "json": ""}])
    rows = [{"bill_id": b, "question_id": q, "question": f"question {q}?", "answer": ""}
            for b in ("IESCO_0001", "KESC_0001") for q in ("Q1", "Q2")]
    csv_io.write_csv(tmp_path / "l2.csv", csv_io.L2_HEADERS, rows)
    return tmp_path


def fake_generate(calls):
    def gen(contents, schema, model=None):
        calls.append(schema.__name__)
        if schema is Extraction:
            return make_extraction()
        qs = json.loads(contents[0].split("QUESTIONS:\n")[1])
        return AnswerSet.model_validate({"answers": [{"question_id": q["question_id"], "answer": f"ans {q['question_id']}"}
                                                    for q in qs]})
    return gen


def test_full_run_writes_valid_csvs_and_uses_cache(workspace, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm, "generate", fake_generate(calls))
    out = workspace / "out"
    rep = pipeline.run_decode(workspace / "bills", workspace / "l1.csv", workspace / "l2.csv", out)
    assert all(r["status"] == "ok" for r in rep.values())
    l1 = csv_io.read_template(out / "level1.csv", csv_io.L1_HEADERS)
    assert json.loads(l1[0]["json"])["provider"] == "IESCO" and "history" not in json.loads(l1[0]["json"])
    assert len(csv_io.read_template(out / "level2.csv", csv_io.L2_HEADERS)) == 4
    n = len(calls)
    pipeline.run_decode(workspace / "bills", workspace / "l1.csv", workspace / "l2.csv", out)
    assert len(calls) == n                      # second run is served from cache


def test_repair_loop_keeps_the_better_extraction(workspace, monkeypatch):
    seq = iter([make_extraction(total_charges=999), make_extraction()])     # bad first, good second
    monkeypatch.setattr(llm, "generate", lambda c, s, m=None: next(seq))
    from billdecoder import extract
    ext, warnings = extract.extract_bill(workspace / "bills" / "IESCO_0001.png", use_fewshot=False)
    assert warnings == [] and ext.total_charges == 1243


def test_one_failing_bill_is_reported_not_fatal(workspace, monkeypatch):
    def gen(contents, schema, model=None):
        raise llm.LLMError("boom")
    monkeypatch.setattr(llm, "generate", gen)
    with pytest.raises(pipeline.PipelineError):
        pipeline.run_decode(workspace / "bills", workspace / "l1.csv", workspace / "l2.csv", workspace / "out")
    rep = json.loads((workspace / "out" / "report.json").read_text())
    assert rep["IESCO_0001"]["status"] == "failed"
