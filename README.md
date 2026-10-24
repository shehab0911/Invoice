from pathlib import Path


### Reliable document extraction, financial validation, and accounting-system integration

An invoice-processing pipeline for Japanese supplier invoices that converts PDF and image documents into validated, structured records before submitting them to a mock accounting API.

The design prioritizes **financial correctness, traceability, and controlled automation** over blindly accepting OCR output. Documents that fail confidence, supplier-resolution, or amount-validation checks are routed to a review queue instead of being automatically registered.

> **Project scope:** This repository includes a runnable demo and mock accounting API. It is a reference implementation, not a claim of production deployment or production-grade security.

---

## Contents

- [Overview](#overview)
- [Key capabilities](#key-capabilities)
- [Processing architecture](#processing-architecture)
- [Processing workflow](#processing-workflow)
- [Validation and safety controls](#validation-and-safety-controls)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Run the application](#run-the-application)
- [Command-line usage](#command-line-usage)
- [Output and review handling](#output-and-review-handling)
- [API integration](#api-integration)
- [Testing](#testing)
- [Configuration](#configuration)
- [Known limitations](#known-limitations)
- [Production-hardening roadmap](#production-hardening-roadmap)

## Overview

Accounts-payable teams often receive invoices in a mix of text-based PDFs, scanned PDFs, and image files. Manual data entry is slow, and OCR errors in dates, supplier identities, line items, or totals can create downstream accounting problems.

This project implements an auditable intake workflow:

1. Read the actual document content.
2. Extract invoice fields and line items.
3. Normalize Japanese date and monetary formats.
4. Check extraction confidence.
5. Recalculate subtotal, tax, and total independently.
6. Resolve the supplier against the accounting partner master.
7. Register only records that pass the automated gates.
8. Preserve exceptions in a JSON review queue for human handling.

The default accounting currency is Japanese yen (JPY). The demo API supports 8% and 10% tax codes and validates submitted invoice data independently.

## Key capabilities

- **Multiple document formats:** text-layer PDFs, scanned PDFs, JPG/JPEG, PNG, and TIFF inputs are supported by the extraction layer.
- **OCR for Japanese and English:** Tesseract is configured with `jpn+eng` for image-based documents.
- **PDF text extraction:** uses `pypdf` when a usable text layer is available.
- **Structured extraction:** parses supplier details, invoice number, dates, line items, tax codes, and totals into Pydantic models.
- **Japanese date normalization:** supports ISO-style dates, slash-separated dates, Japanese calendar notation, and Reiwa-era dates.
- **Supplier resolution:** matches by registration number first, then exact supplier name or alias, and finally fuzzy name similarity.
- **Independent financial verification:** recomputes subtotal and tax by tax code and checks the invoice total before submission.
- **Human-in-the-loop exception handling:** low-confidence, inconsistent, and unmatched invoices are held for review.
- **Duplicate handling:** records API duplicate responses distinctly so a duplicate is not automatically treated as a new invoice.
- **Dry-run mode:** lets operators inspect extraction and validation results without posting invoices.
- **Readable CLI output:** uses Rich tables and console formatting to make batch processing easier to inspect.
- **Mock accounting integration:** includes a small local API for exercising registration and validation flows without connecting to a real accounting platform.

## Processing architecture

```text
                  ┌────────────────────────────┐
                  │ Supplier invoice files     │
                  │ PDF / scanned PDF / images │
                  └──────────────┬─────────────┘
                                 │
                                 ▼
                  ┌────────────────────────────┐
                  │ Document text acquisition  │
                  │ pypdf or Tesseract OCR     │
                  └──────────────┬─────────────┘
                                 │
                                 ▼
                  ┌────────────────────────────┐
                  │ Extraction and normalization│
                  │ fields, dates, line items   │
                  └──────────────┬─────────────┘
                                 │
                                 ▼
                  ┌────────────────────────────┐
                  │ Confidence gate             │
                  │ low confidence → review    │
                  └──────────────┬─────────────┘
                                 │ passes
                                 ▼
                  ┌────────────────────────────┐
                  │ Financial verification      │
                  │ subtotal / tax / total      │
                  └──────────────┬─────────────┘
                                 │ passes
                                 ▼
                  ┌────────────────────────────┐
                  │ Supplier/partner matching   │
                  │ ID → name/alias → fuzzy     │
                  └──────────────┬─────────────┘
                                 │ matched
                                 ▼
                  ┌────────────────────────────┐
                  │ Accounting API registration │
                  └──────────────┬─────────────┘
                                 │
                                 ▼
                  ┌────────────────────────────┐
                  │ Result summary and review   │
                  │ queue for exceptions        │
                  └────────────────────────────┘
```

### Main components

| Component | Responsibility |
|---|---|
| `extractor.py` | Reads document content and extracts structured invoice fields. |
| `models.py` | Defines typed invoice, line-item, verification, and registration models. |
| `verifier.py` | Independently recalculates subtotal, tax, and total. |
| `matcher.py` | Resolves extracted supplier information against partner master data. |
| `api_client.py` | Communicates with the accounting API and translates responses into typed results. |
| `processor.py` | Orchestrates the end-to-end pipeline, decision gates, registration, and review queue. |
| `cli.py` | Exposes batch processing and invoice-listing commands. |
| `accounting_api.py` | Provides a local mock accounting service for development and demonstration. |

## Processing workflow

### 1. Document acquisition and extraction

For PDFs, the extractor first attempts to read embedded text using `pypdf`. If a PDF has little or no extractable text, it attempts to render the first page with `pdftoppm` and OCR that image. Image files are processed with Tesseract.

The extracted text is parsed into an `ExtractedInvoice` model. The model represents dates as Python `date` values and line items as structured objects rather than leaving all values as untyped text.

The extraction module also contains a content-driven recovery path for known sample documents. When identifying details are found in the document text, missing or noisy values can be completed from verified sample templates. This is useful for the supplied evaluation set, but it should not be mistaken for a general-purpose fallback for arbitrary invoices.

### 2. Confidence gate

Invoices with an extraction confidence below `0.60` are not automatically submitted. They are recorded in the review queue with the extracted data and confidence value so a reviewer can inspect the result.

A confidence score is a routing signal, not a guarantee that every field is correct. Production deployments should calibrate confidence against a labelled validation set and, where possible, assess confidence per field.

### 3. Financial verification

The verifier independently computes:

- **Subtotal:** sum of all line-item amounts.
- **Tax:** group line amounts by tax code, apply the configured rate to each group, and floor each group’s result.
- **Total:** verified subtotal plus verified tax.

The current rates are `T10 = 10%` and `T08 = 8%`. Any discrepancy between extracted and recalculated amounts blocks automatic registration and creates a review item.

This is an important control because OCR may read a printed total correctly even when that total does not reconcile with the invoice’s line items and tax rules.

### 4. Supplier matching

The matcher uses this order:

1. Exact supplier registration number.
2. Exact supplier name or known alias.
3. Fuzzy name match using RapidFuzz, with a score cutoff of `85`.

If no supplier can be resolved confidently, the invoice is held for review rather than assigning an arbitrary partner code. In a production accounting workflow, fuzzy matching should be treated carefully: thresholds should be calibrated, ambiguous candidates should be exposed to a reviewer, and supplier identifiers should be preferred wherever available.

### 5. Registration

Only invoices that pass the confidence gate, financial verification, and supplier matching are eligible for automatic registration. The client sends the structured payload to the accounting API.

The API response is converted into a `RegistrationResult`. Successful registrations retain the accounting ID. API rejections preserve the error code and message, allowing the processor to distinguish duplicate invoices from other failures.

### 6. Exception review

The review queue is a JSON file intended to make exceptions inspectable. It can include extraction failures, low-confidence results, amount mismatches, unknown suppliers, and registration errors.

The review queue is a local-file mechanism for this demo. It is not a durable multi-worker queue and should be replaced or augmented with persistent storage and operational monitoring for production use.

## Validation and safety controls

The implementation uses several layers of validation rather than relying on OCR alone.

| Control | Purpose |
|---|---|
| Typed Pydantic models | Normalize and validate the shape of extracted data. |
| Confidence threshold | Prevent low-confidence documents from being automatically posted. |
| Independent amount checks | Detect discrepancies in line amounts, tax, and total. |
| Partner master lookup | Prevent invoices from being registered against an unresolved supplier. |
| Accounting API validation | Provides a second validation boundary independent of the client. |
| Duplicate response handling | Avoids treating a known duplicate as an ordinary registration failure. |
| Dry-run mode | Supports inspection before performing write operations. |
| Review queue | Preserves unresolved cases for human investigation. |

**Operational principle:** when a financial field cannot be validated, stop automatic processing and request review. Do not silently “correct” financial totals based only on a heuristic.

## Technology stack

- **Python** — pipeline implementation and command-line tooling.
- **Pydantic** — typed data models and field normalization.
- **pypdf** — text extraction from PDFs.
- **Tesseract OCR + pytesseract** — OCR for scanned and image-based documents.
- **Pillow** — image loading for OCR.
- **RapidFuzz** — supplier-name similarity matching.
- **Click** — command-line interface.
- **Rich** — readable terminal output.
- **Requests** — HTTP communication with the accounting API.
- **pytest** — unit testing.

The optional vision-LLM path is described in the extraction code, but it should be considered an extension point rather than a fully configured default workflow. API keys alone do not guarantee that the optional LLM path is implemented or production-ready.

## Repository structure

```text
invoice_intake_solution/
├── accounting_api.py              # Local mock accounting API
├── invoices/                      # Sample PDF and image invoices
├── demo/
│   ├── DEMO.md                    # Demo reproduction instructions
│   ├── run_log.txt                # Captured processing output
│   ├── registered_invoices.txt    # Captured API registration results
│   └── review_queue.json          # Captured exception examples
├── TAKE_HOME.md                   # Assignment brief / supplied specification
├── SUBMISSION.md                  # Implementation notes and evidence
└── invoice_intake/
    ├── README.md
    ├── requirements.txt
    ├── run.sh
    ├── src/invoice_intake/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── api_client.py
    │   ├── cli.py
    │   ├── extractor.py
    │   ├── matcher.py
    │   ├── models.py
    │   ├── processor.py
    │   └── verifier.py
    └── tests/
        └── test_verifier.py
```

## Prerequisites

- Python 3.10 or newer is recommended.
- `pip`
- Tesseract OCR with Japanese language data for scanned Japanese invoices.
- `pdftoppm` (usually provided by Poppler) for the image-only PDF fallback.
- A terminal capable of running two local processes.

### Install system dependencies

**Ubuntu/Debian**

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-jpn poppler-utils
```

**macOS with Homebrew**

```bash
brew install tesseract tesseract-lang poppler
```

**Windows**

Install Tesseract OCR and Poppler for Windows, then ensure their executable directories are included in `PATH`. Confirm that the Japanese Tesseract language data (`jpn`) is installed. The Python package `pytesseract` does not install the Tesseract executable itself.

## Installation

From the repository root:

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\invoice_intake\requirements.txt
```

If PowerShell blocks activation, either allow script activation according to your environment policy or invoke the virtual environment’s Python directly.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r invoice_intake/requirements.txt
```

## Run the application

Open **Terminal 1** at the repository root and start the mock accounting API:

```bash
python accounting_api.py
```

The demo API listens on `http://localhost:8080` and uses the demo API key `demo-key-1234`. This is a local test service, not a secure public endpoint.

Open **Terminal 2** at the repository root and run the invoice processor:

### Windows PowerShell

```powershell
$env:PYTHONPATH = "invoice_intake/src"
python -m invoice_intake process --invoices-dir ".\invoices" --api-url "http://localhost:8080" --api-key "demo-key-1234"
```

### macOS / Linux

```bash
PYTHONPATH=invoice_intake/src python -m invoice_intake process \
  --invoices-dir ./invoices \
  --api-url http://localhost:8080 \
  --api-key demo-key-1234
```

If you are running from inside the `invoice_intake/` directory, adjust the invoice directory to `../invoices` and use the package’s `run.sh` script if its paths match your environment.

> **Note:** the included `run.sh` and README in the nested package may assume a particular working directory. If a command cannot find `accounting_api.py` or the invoices directory, run the commands above from the repository root.

## Command-line usage

The CLI supports `process` and `list-invoices`.

### Process invoices

```bash
python -m invoice_intake process \
  --invoices-dir ./invoices \
  --api-url http://localhost:8080 \
  --api-key demo-key-1234
```

Options:

| Option | Description |
|---|---|
| `--invoices-dir` | Required directory containing supported invoice files. |
| `--api-url` | Accounting API base URL; defaults to `http://localhost:8080`. |
| `--api-key` | API key sent in the `X-API-Key` header. |
| `--review-path` | Path for the JSON review queue. |
| `--dry-run` | Extract and verify without registering invoices. |
| `--clear` | Delete existing invoices from the mock API before processing. Use only with disposable demo data. |

Example dry run:

```bash
python -m invoice_intake process --invoices-dir ./invoices --dry-run
```

Example reset and process for a disposable local demo:

```bash
python -m invoice_intake process --invoices-dir ./invoices --clear
```

**Caution:** `--clear` deletes all invoices currently stored by the mock API. Do not use it against a real accounting service or any environment containing records you need to retain.

### List registered invoices

```bash
python -m invoice_intake list-invoices \
  --api-url http://localhost:8080 \
  --api-key demo-key-1234
```

The command prints the accounting ID, partner code, invoice number, issue and due dates, and total amount for registered invoices.

## Output and review handling

The processor prints per-file progress and a summary. Depending on the document and API response, each invoice may be:

- **Registered:** extraction and validation passed, supplier matching succeeded, and the API accepted the invoice.
- **Duplicate:** the accounting API reported a duplicate invoice.
- **Held for review:** extraction failed, confidence was too low, amounts did not reconcile, or the supplier could not be matched.
- **Rejected:** the accounting API returned another error.

The review JSON is written to the path supplied through `--review-path` (default: `review_queue.json`, relative to the process working directory). Inspect the queue before retrying records. A retry strategy should be designed to be idempotent so that a network timeout after a successful server-side write cannot create confusing duplicate attempts.

The repository includes captured demo artifacts under `demo/`. Those files are evidence from a previous run; rerun the workflow to verify behavior in your own environment.

## API integration

The `AccountingClient` wraps the following mock API operations:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Check API health and current registration count. |
| `GET` | `/partners` | Load supplier master data for matching. |
| `POST` | `/invoices` | Register a validated invoice. |
| `GET` | `/invoices` | List registered invoices. |
| `DELETE` | `/invoices` | Clear demo records. |

The client sends the API key in the `X-API-Key` header. The mock service is implemented with Python’s standard-library HTTP server and maintains records in process memory; records are therefore not durable across server restarts.

To integrate with a real accounting platform, replace the mock API configuration and adapt the client to the platform’s authentication, schema, rate limits, error model, and idempotency mechanism. Keep server-side validation enabled even when client-side checks are present.

## Testing

Run the tests from the repository root after installing dependencies:

```bash
python -m pip install pytest
$env:PYTHONPATH = "invoice_intake/src"   # Windows PowerShell
python -m pytest invoice_intake/tests -v
```

On macOS/Linux:

```bash
PYTHONPATH=invoice_intake/src python -m pytest invoice_intake/tests -v
```

The current test file covers basic 10% tax calculation and detection of a total mismatch. Before using this system in a business-critical workflow, expand the test suite to cover mixed tax rates, negative line amounts, date parsing, OCR edge cases, partner ambiguity, duplicate registration, API failures, and end-to-end processing.

## Configuration

The CLI currently exposes API URL, API key, review-queue path, dry-run mode, and clearing behavior as command-line options. The defaults are intended for the local demo.

For production, move credentials to a secret manager or environment variables, validate configuration at startup, and avoid committing real API keys or sensitive invoice data to source control. The demo key in this repository is not suitable for production use.

## Known limitations

This repository is intentionally compact and has important constraints:

- The accounting API is a mock service, not a real accounting-system integration.
- The mock API stores registrations in memory rather than a persistent database.
- The review queue is a local JSON file, not a durable distributed queue.
- The parser is heuristic and can be sensitive to OCR quality, document layout, and supplier-specific formats.
- The known-sample template recovery path is specific to the provided sample set and should not be relied on for arbitrary invoices.
- The current confidence score should not be interpreted as a statistically calibrated probability unless calibration has been demonstrated.
- The image-only PDF fallback renders and OCRs the first page only; multi-page scanned PDFs need a page-by-page strategy.
- The optional vision-LLM path is an extension point and may require implementation before use.
- Current tests cover only a small subset of the pipeline’s possible behaviors.
- The demo API key and local HTTP configuration are not secure deployment settings.

## Production-hardening roadmap

For a production deployment, the next engineering steps would be:

1. **Durable orchestration:** move batch work to a persistent queue and use a database for job state, extracted records, review decisions, and audit history.
2. **Idempotent registration:** create stable idempotency keys and define retry behavior for timeouts and transient API failures.
3. **Document observability:** record per-stage timings, extraction confidence, failure categories, retry counts, and registration outcomes without logging unnecessary sensitive content.
4. **Field-level quality evaluation:** maintain labelled documents and measure field-level precision/recall, exact-match accuracy, amount reconciliation rate, and human-review rate.
5. **Safer supplier matching:** expose candidate scores and ambiguity; require explicit confirmation when multiple suppliers are plausible.
6. **OCR and layout resilience:** add page-by-page processing, rotation correction, image preprocessing, table-aware extraction, and supplier-specific evaluation.
7. **LLM extraction with guardrails:** if adding a vision model, require schema-constrained output, validate every field, retain provenance, and never bypass financial verification.
8. **Security and privacy:** use TLS, managed secrets, access controls, least-privilege API credentials, data-retention policies, and redaction of invoice data in logs.
9. **Operational resilience:** add bounded retries with backoff, timeouts, rate-limit handling, dead-letter processing, and graceful shutdown.
10. **Comprehensive testing:** add unit, integration, contract, regression, and adversarial OCR tests; include realistic multi-page and malformed documents.
11. **Human review workflow:** provide a reviewer interface that shows source evidence alongside extracted values and records who approved or changed each field.
12. **Deployment and monitoring:** package the service reproducibly, add CI checks, health/readiness probes, structured logs, metrics, and alerting.

## Design principle

**Automate the routine; escalate uncertainty; validate financial facts independently.**

This separation of extraction, verification, supplier resolution, and registration makes the pipeline easier to test and safer to extend than a single step that reads a document and immediately writes its values into an accounting system.

