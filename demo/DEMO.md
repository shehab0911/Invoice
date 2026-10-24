# Demo evidence

## How to reproduce

```bash
# Terminal 1
python3 accounting_api.py

# Terminal 2
cd invoice_intake
chmod +x run.sh
./run.sh
```

## Observed result (this run)

9 invoices registered, 1 duplicate rejected, 1 amount-mismatch held for review,
1 unknown-partner held for review.

See:
- `run_log.txt` – full terminal output of the processing run
- `registered_invoices.txt` – `GET /invoices` after the run
- `review_queue.json` – items that need human attention

For a formal submission, replace these text captures with a ≤3 min screen recording
or screenshots of the same terminal session.
