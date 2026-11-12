# WTQ Utility Bill Decoder

Reads a photo or scan of a Pakistani electricity bill (K-Electric, LESCO, IESCO) and
1. extracts the bill into schema-validated JSON (Level 1), and
2. answers customer questions about it in plain English (Level 2).

Built solo for the 10Pearls Women Tech Quest 2026 (Build with AI) build track, then rebuilt
with a verification layer and tests. Python 3.12, Gemini (`gemini-3.5-flash-lite`).

## How it works

```
bill image
   |  extract.py   Gemini reads the image; output is FORCED into a Pydantic schema (structured output)
   v
Extraction  (Level 1 fields + month-by-month history table)
   |  checks.py    deterministic checks: readings vs units, line items vs printed subtotals,
   |               date validity. On failure the model re-reads once; the better result is kept.
   v
verified Extraction ---> Level 1 JSON (history and extras removed)
   |  analytics.py ALL arithmetic in plain Python: averages, peak month, summer vs winter,
   |               trend, payment status, next-month estimate, even monthly budget ...
   v
facts (dict)
   |  answer.py    Gemini turns the facts into 2-4 sentence English answers. It never does the maths.
   v
Level 2 answers
```

Why: in the first version one model call did everything and made arithmetic and column mistakes
(for example it summed the bill-amount column instead of the units column). The model is now only
used for reading and writing; numbers come from code that is unit-tested.

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your Gemini API key in .env
python -m pytest -q           # 30 tests, no API key needed
```

## Run

```bash
# fill the two CSV templates from a folder of bill images
python run.py decode --bills test/bills --level1 test/csv/level1.csv --level2 test/csv/level2.csv --out output

# build a hand-labelled gold set, then score the extractor against it
python run.py draft --bills train/bills --bill-id KESC_0004     # writes eval/gold/KESC_0004.draft.json
#   open the image, correct every value, rename to KESC_0004.json
python run.py eval --bills train/bills
```

Outputs: `output/level1.csv`, `output/level2.csv`, `output/report.json` (bills with consistency
warnings are marked `needs_review`), `output/facts/<bill>.json` (the numbers behind each answer).
Runs are resumable: finished bills are cached in `.cache/`. Use `--no-cache` to force fresh calls.

## Layout

```
run.py                  CLI: decode / eval / draft
billdecoder/
  schema.py             Pydantic models (Level 1 + extras)
  llm.py                Gemini call, structured output, retry with backoff on 429/5xx
  extract.py            prompt, image loading (EXIF fix), one worked example, repair loop
  checks.py             normalisation rules + reconciliation checks
  analytics.py          Level 2 maths
  answer.py             facts -> English answers
  csv_io.py             template reading, writing, output verification
  pipeline.py           ties it together, caching, report
  evaluate.py           field-level scorer (text exact, numbers +-1)
eval/gold/              hand-labelled expected JSON
tests/                  30 tests, including regression tests for the v1 mistakes and a mocked end-to-end run
```

## Results

Run `python run.py eval --bills train/bills` after labelling bills and paste the table here.

| Model | Labelled bills | Mean field accuracy |
|---|---|---|
| gemini-3.5-flash-lite | _fill in_ | _fill in_ |

## Known limitations

- The IESCO/LESCO charge-line convention (energy = Total Electricity Charges, subsidy negative,
  Total FPA listed as a separate fpa charge, single combined tax -> `total_taxes`) is my reading of the task guide.
  Verify it against your hand-labelled bills.
- "Last 12 months" means the 12 months before the current bill month. Where a question can be read
  two ways, the answer states which reading was used.
- Estimates (next month's units, a bill at last month's usage) are simple and labelled as estimates.
  Real tariffs use slabs, which the bill does not fully show.
- Quality depends on image readability. Bills with warnings are flagged, not silently corrected.

## AI usage

- Application model: Gemini 3.5 Flash-Lite via the `google-genai` SDK. No other model or extraction service.
- Development: ChatGPT and Claude were used as coding and debugging assistants.
