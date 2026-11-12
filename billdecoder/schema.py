"""Typed schema. Gemini is forced to return exactly this shape (structured output),
so there is no 'did the model return valid JSON?' guessing."""
from typing import Literal, Optional

from pydantic import BaseModel

ChargeType = Literal["energy", "fixed", "fpa", "quarterly_adjustment",
                     "surcharge", "meter_rent", "subsidy", "other"]
TaxType = Literal["gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"]


class Charge(BaseModel):
    type: ChargeType
    amount: float


class Tax(BaseModel):
    type: TaxType
    amount: float


class HistoryRow(BaseModel):
    """One month from the bill's usage / billing history. Month is YYYY-MM."""
    month: str
    units: Optional[float]
    bill_amount: Optional[float]
    payment: Optional[float]


class LateSurcharge(BaseModel):
    description: str                 # e.g. "5% LPS if paid 22-Apr to 24-Apr"
    surcharge_amount: Optional[float]
    payable_amount: Optional[float]


class Bill(BaseModel):
    """Level 1 output: exactly the fields the task asks for."""
    provider: Literal["KE", "LESCO", "IESCO"]
    tariff: Optional[str]
    sanctioned_load_kw: Optional[float]
    bill_month: Optional[str]
    reading_date: Optional[str]
    issue_date: Optional[str]
    due_date: Optional[str]
    previous_reading: Optional[float]
    current_reading: Optional[float]
    units_consumed: Optional[float]
    charges: list[Charge]
    total_charges: Optional[float]
    taxes: list[Tax]
    total_taxes: Optional[float]
    current_bill: Optional[float]
    arrears: Optional[float]
    payable_within_due_date: Optional[float]
    payable_after_due_date: Optional[float]


class Extraction(Bill):
    """What the model returns: the Level 1 fields PLUS extra facts needed for Level 2.
    The extras are removed before Level 1 is written (see Extraction.to_level1)."""
    history: list[HistoryRow]
    net_metering_evidence: Optional[str]   # text on the bill showing solar/net-metering/export, else null
    fpa_note: Optional[str]                # printed note naming the FPA/FCA month, else null
    late_payment: list[LateSurcharge]

    def to_level1(self) -> dict:
        data = self.model_dump(include=set(Bill.model_fields), mode="json")
        return _tidy_numbers(data)


class QA(BaseModel):
    question_id: str
    answer: str


class AnswerSet(BaseModel):
    answers: list[QA]


def _tidy_numbers(obj):
    """3.0 -> 3, so the JSON looks like the guide's examples."""
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _tidy_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_tidy_numbers(v) for v in obj]
    return obj
