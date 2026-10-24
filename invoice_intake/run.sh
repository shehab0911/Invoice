#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

INVOICES_DIR="${ROOT}/../invoices"
if [[ ! -d "$INVOICES_DIR" ]]; then
  echo "Invoices directory not found at $INVOICES_DIR"
  exit 1
fi

echo "=== Invoice Intake ==="
echo "API : http://localhost:8080"
echo "Dir : $INVOICES_DIR"
echo

# Soft-install if needed (ignore failures so missing optional deps don't block)
python3 -m pip install -q -r requirements.txt --user 2>/dev/null || true

python3 -m invoice_intake process \
  --invoices-dir "$INVOICES_DIR" \
  --api-url http://localhost:8080 \
  --api-key demo-key-1234 \
  --clear \
  "$@"
