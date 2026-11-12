"""Step 3: facts (computed in Python) -> plain-English answers. The LLM only writes prose."""
import json
import logging

from . import llm
from .schema import AnswerSet, Extraction

log = logging.getLogger("billdecoder")

PROMPT_VERSION = "v2"

PROMPT = """You answer a customer's questions about their electricity bill in plain English.

You are given (1) the bill's extracted figures and (2) FACTS that were already calculated for you.
RULES
- Use ONLY the figures and facts below. Never recalculate. Never use outside tariff or rate knowledge.
- Quote the exact numbers from the facts. Mention the months or counts they are based on.
- Estimates (next month's units, a bill at last month's usage, an even monthly budget) must be
  labelled 'estimate', with one sentence on how it was calculated.
- If a question can be read two ways, say which reading you used (and give the other if the facts have it).
- If a needed fact is null, missing or empty, say plainly that the bill does not show it. Do not guess.
- 2 to 4 sentences per answer. English only. No names, addresses or ID numbers.
- Write the final answer directly. Never think out loud ('wait', 'let me').

WHICH FACTS ANSWER WHAT
- standard vs net-metered: net_metering_evidence (null => standard connection, say no solar/export wording was found)
- highest month: peak_month, peak_units, current_exceeds_peak
- fuel adjustment: fpa_charges, fpa_note
- late payment: late_payment, payable_within_due_date, payable_after_due_date
- vs same month last year: same_month_last_year(_units), vs_same_month_last_year_diff
- average and comparison: avg_monthly_units, history_months_with_units, current_vs_avg_diff/pct
- summer vs winter: summer_*/winter_* (state the months used, give total difference and per-month difference)
- paying every bill: payments (paid_in_full_or_more, shown_as_zero, payment_not_shown, ...)
- last 3 months trend: last3_units, last3_steps, last3_overall, last3_then_current_note
- next month units: next_month_estimate_units, next_month_reference_values, next_month_method
- even monthly cost: set_aside_per_month, billed_months_available, set_aside_is_full_year
- bill at last month's usage: bill_estimate_*, last_month_units, bill_estimate_note
- tax questions: tax_share_pct plus the bill figures
"""


def _bad(answer: str) -> bool:
    a = answer.strip().lower()
    return (not a) or a.startswith(("wait", "hmm", "let me")) or " wait," in a or "let me re" in a


def answer_questions(ext: Extraction, facts: dict, questions: list[dict], model: str | None = None) -> dict[str, str]:
    """questions: [{"question_id": "Q1", "question": "..."}]. Returns {question_id: answer}."""
    wanted = [q["question_id"] for q in questions]
    bill_view = ext.to_level1()
    base = (PROMPT +
            "\nBILL FIGURES:\n" + json.dumps(bill_view) +
            "\n\nFACTS:\n" + json.dumps(facts, default=str) +
            "\n\nQUESTIONS:\n" + json.dumps(questions, ensure_ascii=False))

    result: dict[str, str] = {}
    problems: list[str] = []
    for attempt in range(2):
        prompt = base if attempt == 0 else base + "\n\nFix these problems and answer every question: " + "; ".join(problems)
        out = llm.generate([prompt], AnswerSet, model)
        problems = []
        for qa in out.answers:
            if qa.question_id in wanted and not _bad(qa.answer):
                result[qa.question_id] = qa.answer.strip()
        problems = [f"{q} missing or unusable" for q in wanted if q not in result]
        if not problems:
            break
    for q in wanted:
        if q not in result:
            log.warning("no usable answer for %s after retry; using safe fallback", q)
            result[q] = "I could not work out a reliable answer to this from the bill."
    return result
