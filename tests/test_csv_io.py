import json

import pytest

from billdecoder import csv_io


def test_roundtrip_with_quotes_and_commas(tmp_path):
    tpl = [{"bill_id": "A_1", "json": ""}]
    rows = csv_io.level1_rows(tpl, {"A_1": {"provider": "KE", "note": 'a "quoted", value'}})
    p = tmp_path / "level1.csv"
    csv_io.write_csv(p, csv_io.L1_HEADERS, rows)
    csv_io.verify_output(p, csv_io.L1_HEADERS, tpl, ["bill_id"])
    back = csv_io.read_template(p, csv_io.L1_HEADERS)
    assert json.loads(back[0]["json"])["note"] == 'a "quoted", value'
    assert "\n" not in back[0]["json"]


def test_verify_rejects_empty_answer(tmp_path):
    tpl = [{"bill_id": "A_1", "question_id": "Q1", "question": "q?", "answer": ""}]
    p = tmp_path / "level2.csv"
    csv_io.write_csv(p, csv_io.L2_HEADERS, csv_io.level2_rows(tpl, {"A_1": {"Q1": ""}}))
    with pytest.raises(ValueError):
        csv_io.verify_output(p, csv_io.L2_HEADERS, tpl, ["bill_id", "question_id", "question"])


def test_wrong_headers_rejected(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        csv_io.read_template(p, csv_io.L1_HEADERS)
