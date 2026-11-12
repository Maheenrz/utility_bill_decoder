
"""Step 1 of the pipeline: image -> validated, normalised, checked Extraction."""
import hashlib
import json
import logging
from pathlib import Path

from PIL import Image, ImageOps

from . import config, llm
from .checks import check, normalize
from .schema import Extraction

log = logging.getLogger("billdecoder")

PROMPT_VERSION = "v10"

PROMPT = """You read Pakistani electricity bills (K-Electric = KE, LESCO, IESCO) from images
(scans, screenshots or tilted phone photos, sometimes partly in Urdu) and return structured data.

GENERAL RULES
- Copy values exactly as printed. Never recalculate, round or 'correct' a printed value.
- Amounts are plain numbers in PKR: no commas, no currency text.
- Credits (e.g. 38209CR) and subsidies are NEGATIVE numbers.
- A CR suffix means the amount is negative. Preserve this sign in every field,
  including payable amounts and late_payment.payable_amount.
- Never drop a CR suffix or convert a negative credit into a positive amount.
- Dates are YYYY-MM-DD. bill_month is YYYY-MM (MAR 26 -> 2026-03). Two-digit years are 20xx.
- Use null for anything not printed, blank, covered by a grey box, or unreadable. Never guess.
- Never output names, addresses, CNIC, account, reference, consumer or meter numbers.
- charges: one entry per line of the charges section. Skip blank lines and lines printed as 0.
  Keep repeated types as separate entries.
- arrears: previous dues carried forward, keep the printed sign; null if blank.
- sanctioned_load_kw comes from 'Sanc Load' / 'San Load' / 'S.Load'.

PAYABLE AMOUNTS AND LATE PAYMENT
- payable_within_due_date: copy the explicitly printed payable amount, preserving its sign.
- payable_after_due_date: if several actual after-due-date payable amounts are printed,
  use the highest, preserving its printed sign.
- If an after-due-date option explicitly says "NOT TO BE PAID",
  payable_after_due_date = null and that option's late_payment.payable_amount = null.
- Apply "NOT TO BE PAID" only to the specific option or amount it refers to.
  Do not apply it to another payment option.
- If a numeric payable amount is explicitly printed, preserve it exactly,
  including an explicitly printed 0 or 0.00.
- A zero surcharge does NOT mean the payable amount is zero or missing.
- Do not infer a payable amount from the surcharge, current bill, arrears,
  or another payment option.
- For late_payment, extract each option's description, surcharge_amount,
  and payable_amount separately. Preserve negative signs and explicit zero values.
- If the payable amount for an option is blank or explicitly marked "NOT TO BE PAID",
  use null for that option's payable_amount.

- NET METERING / MULTIPLE REGISTERS:
  - Identify whether the bill contains multiple separate meter-register rows.
  - Each row represents an individual register, not necessarily the property's
    overall consumption.
  - A row's units value is NOT automatically the property's units_consumed.
  - NEVER copy the first register's units into units_consumed.
  - NEVER use one register's previous/current readings as the overall readings.
  - If multiple register rows are present:
      previous_reading = null
      current_reading = null
      units_consumed = a separate, explicitly labelled overall current-month
                       consumption figure, ONLY if clearly printed.
  - If no separate overall consumption figure is printed, units_consumed = null.
  - Do not add individual register units together to manufacture an overall total.
  - Do not confuse historical monthly units with current-month overall consumption.
  - Apply these rules even when one register's units are more prominent or easier to read.

LAYOUT NOTES
K-Electric:
  - Charge lines (Fixed, Variable upto N units, Quarterly adjustment, FCA, Additional surcharge) are
    listed under 'Electricity Charges' which has a printed subtotal = total_charges.
  - 'Taxes and Duties' lists ED (electricity_duty), Sales Tax (gst), MUCT/KMC (municipal_tax);
    its printed subtotal = total_taxes. 'FCA' means type fpa.
  - History: the 13-month bar chart gives UNITS per month (the rightmost bar is the current month;
    year labels sit under the bars). 'Billing & Payment History' (MM/YY) gives billed amount and
    payment for only the last ~3 months. Merge both into `history` by month.

IESCO and LESCO NEWER layout (box 'BILL CHARGES BREAKDOWN' with 'Net Electricity Charges'):
  - charges = [ energy = 'Total Electricity Charges', subsidy = -(Subsidies) only when it is not 0,
    fpa = 'Total FPA' when it is not 0 ]. total_charges = 'Net Electricity Charges' (the printed subtotal).
    'Total FPA' is a separate line that is added on top: Grand Total = Current Bill + Arrears + Total FPA.
  - Only ONE combined 'Taxes' figure is printed: taxes = [] and total_taxes = that figure.
  - The percentages printed beside 'Net Electricity Charges' and 'Taxes' (for example 77.78 and 22.22)
    are NOT amounts. The amount is the larger number on the same row. total_taxes is never a percentage.
  - On a tilted or folded photo the rows can look shifted. Read each value by its row label, and
    check that Net Electricity Charges + Taxes = Current Bill. If not, re-read.
  - current_bill = 'Current Bill'; arrears = 'Arrears'; payable_within_due_date = 'Payable within due date'.
  - 'Bill History' has columns MONTH, STATUS, UNITS, BILL (RS.), PAYMENT (RS.), in two side-by-side
    tables (read left then right). UNITS and BILL are different columns: never mix them up.

Older LESCO layout (boxes 'LESCO CHARGES', 'GOVT. CHARGES', 'TOTAL CHARGES'):
  - LESCO CHARGES column: 'Cost of Electricity' = energy, 'Meter Rent' / 'Service Rent' = meter_rent,
    'Fuel Price Adjustment' = fpa (NOT other), 'F.C Surcharge' = surcharge,
    'Quarterly Tariff Adjustment' = quarterly_adjustment, 'Fixed Charges' = fixed.
    Skip blank lines and the 'Units Consumed' line (it is a unit count, not money).
    total_charges = the TOTAL at the bottom of that column.
  - GOVT. CHARGES column: Electricity Duty and 'ED on FPA' = electricity_duty; GST and 'GST on FPA' = gst;
    Income Tax = income_tax; Extra / Further Tax and their 'on FPA' lines = other_tax.
    total_taxes = the TOTAL at the bottom of that column.
    Unlike the newer layout, taxes ARE itemised here: list every non-blank, non-zero line.
    taxes must NOT be [] for this layout.
  - current_bill = the printed 'Current Bill' even if it differs from charges + taxes. Blank arrears = null.
  - payable_after_due_date: use the highest of the printed 'After <date>' amounts,
    unless the relevant amount is explicitly marked 'NOT TO BE PAID', in which case use null.
  - Its history table has columns MONTH, UNITS, BILL, ADJ., PAYMENT. 'EX' is a status marker, not a number.

EXTRA FIELDS (used to answer customer questions later)
- history: every month visible in any history table/chart. month = YYYY-MM; units; bill_amount;
  payment (blank -> null, printed 0 -> 0). null for columns that layout does not show.
- net_metering_evidence: copy the words on the bill showing solar / net metering / export units /
  green meter; null if there are none.
- fpa_note: copy the printed label or note saying which month the FPA/FCA relates to
  (e.g. 'FCA Feb-26', 'FPA for July 26'); null if none.
- late_payment: each late-payment option: description (percentage and date window), surcharge_amount,
  payable_amount. Preserve CR signs and explicitly printed zero payable amounts.
"""


def load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # phone photos are often stored rotated
    img = img.convert("RGB")
    if max(img.size) > config.MAX_IMAGE_SIDE:
        img.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE))
    return img


def find_image(bills_dir: Path, bill_id: str) -> Path:
    hits = [
        p for p in Path(bills_dir).iterdir()
        if p.is_file()
        and p.stem == bill_id
        and p.suffix.lower() in config.IMAGE_SUFFIXES
    ]
    if len(hits) != 1:
        raise FileNotFoundError(
            f"expected exactly one image for '{bill_id}' in {bills_dir}, found {len(hits)}"
        )
    return hits[0]


def _fewshot_parts(image_path: Path) -> list:
    """One worked example (the guide's KESC_0008 bill + its correct values), skipped when the
    bill being read IS that example."""
    if not (config.FEWSHOT_BILL.is_file() and config.FEWSHOT_GOLD.is_file()):
        return []
    if image_path.resolve() == config.FEWSHOT_BILL.resolve():
        return []
    gold = json.loads(config.FEWSHOT_GOLD.read_text(encoding="utf-8"))
    return [
        "EXAMPLE. This bill:",
        load_image(config.FEWSHOT_BILL),
        "has these correct values for the core fields:",
        json.dumps(gold),
        "Now read the NEXT bill the same way:",
    ]


def cache_key(image_path: Path, model: str, use_fewshot: bool) -> str:
    h = hashlib.sha256()
    h.update(image_path.read_bytes())
    h.update(f"{model}|{PROMPT_VERSION}|{PROMPT}|{use_fewshot}".encode())
    return h.hexdigest()[:20]


def extract_bill(
    image_path: Path,
    model: str | None = None,
    use_fewshot: bool = True,
) -> tuple[Extraction, list[str]]:
    """Returns (extraction, remaining_warnings). One repair attempt if the checks fail."""
    model = model or config.MODEL_NAME
    contents = [PROMPT]
    if use_fewshot:
        contents += _fewshot_parts(image_path)
    contents.append(load_image(image_path))

    ext = normalize(llm.generate(contents, Extraction, model))
    warnings = check(ext)
    if not warnings:
        return ext, warnings

    log.info(
        "%s: %d consistency warning(s), asking the model to re-read once",
        image_path.stem,
        len(warnings),
    )
    feedback = (
        "Your previous answer was:\n"
        + ext.model_dump_json()
        + "\n\nThese automatic checks failed:\n- "
        + "\n- ".join(warnings)
        + "\n\nRe-read the image carefully and fix genuine READING mistakes "
        "(wrong digit, wrong column, missed line). If the bill itself prints "
        "values that do not add up, keep the printed values. Return the full corrected object."
    )
    try:
        ext2 = normalize(llm.generate(contents + [feedback], Extraction, model))
        w2 = check(ext2)
        if len(w2) <= len(warnings):
            return ext2, w2
    except llm.LLMError as exc:
        log.warning(
            "%s: repair attempt failed (%s); keeping first extraction",
            image_path.stem,
            exc,
        )
    return ext, warnings
