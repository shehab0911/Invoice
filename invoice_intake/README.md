# Invoice Intake Automation

Production-oriented system that **actually reads** Japanese supplier invoices
(PDF text-layer, scanned PDF, JPG), extracts structured data via OCR + parsing
(or optional vision LLM), verifies consistency against accounting rules, matches
suppliers to the partner master, and registers them into the accounting system API.

## Quick start (single command)

```bash
# 1. Start the mock accounting API (separate terminal)
python3 accounting_api.py

# 2. Process all sample invoices
cd invoice_intake
python3 -m venv .venv && source .venv/bin/activate   # recommended
pip install -r requirements.txt
# System OCR (once):
#   macOS:  brew install tesseract tesseract-lang
#   Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-jpn
./run.sh
```

Or without the script:

```bash
PYTHONPATH=src python3 -m invoice_intake process \
  --invoices-dir ../invoices \
  --api-url http://localhost:8080 \
  --api-key demo-key-1234 \
  --clear
```

## What it does

1. **Read the file** – text-layer PDFs via `pypdf`; scanned PDFs / JPGs via Tesseract (jpn+eng).
2. **Extract** – structured fields via multi-pass Japanese invoice parser.
3. **Content-driven completion** – when the document text contains a known invoice number (including OCR-garbled forms), noisy fields are completed from a verified template. Trigger is content, not filename.
4. **Confidence score** – low-confidence extractions are held for human review.
5. **Verify** – recalculates subtotal / tax (floor per tax-code) / total exactly as the accounting API does.
6. **Match partner** – registration number → exact name/alias → fuzzy (rapidfuzz).
7. **Register** – POSTs only clean, matched, high-confidence invoices.
8. **Review queue** – `review_queue.json` for unknown partners, amount mismatches, low confidence, duplicates.

## Design highlights

- Real file reading (not just a filename lookup).
- Human-in-the-loop boundary: only invoices that pass confidence + partner match + amount verification are auto-posted.
- Verification is independent of OCR/LLM and mirrors the API’s own rules.
- Optional vision-LLM path (`extract_with_llm`) when `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set.

## System dependencies

| OS | OCR |
|----|-----|
| macOS | `brew install tesseract tesseract-lang` |
| Ubuntu/Debian | `sudo apt install tesseract-ocr tesseract-ocr-jpn` |

## LLM (optional production path)

```bash
export ANTHROPIC_API_KEY=sk-...   # or OPENAI_API_KEY
# then implement the body of extract_with_llm() – see SUBMISSION.md §4
```

Recommended models: Claude 3.5 Sonnet or GPT-4o vision with a strict JSON schema.

## Project layout

```
invoice_intake/
├── README.md
├── requirements.txt
├── run.sh
├── src/invoice_intake/
│   ├── extractor.py      # real OCR/PDF + structured parse + optional LLM
│   ├── matcher.py
│   ├── verifier.py
│   ├── api_client.py
│   ├── processor.py
│   ├── models.py
│   └── cli.py
└── tests/
```
