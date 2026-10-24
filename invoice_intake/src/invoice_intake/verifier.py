"""Client-side amount verification that mirrors the accounting API rules."""

from __future__ import annotations

import math
from collections import defaultdict

from .models import ExtractedInvoice, TaxCode, VerificationResult

TAX_RATES = {TaxCode.T10: 0.10, TaxCode.T08: 0.08}


def verify(invoice: ExtractedInvoice) -> VerificationResult:
    """
    Recalculate subtotal / tax / total exactly as the mock accounting API does:
    - subtotal = sum of line amounts
    - tax is computed per tax_code on that code's subtotal, then floored
    - total = subtotal + tax
    """
    messages: list[str] = []
    expected_subtotal = sum(line.amount for line in invoice.lines)

    if invoice.subtotal != expected_subtotal:
        messages.append(
            f"subtotal mismatch: extracted={invoice.subtotal}, "
            f"sum(lines)={expected_subtotal}"
        )

    subtotal_by_code: dict[TaxCode, int] = defaultdict(int)
    for line in invoice.lines:
        subtotal_by_code[line.tax_code] += line.amount

    tax_by_code = {
        code: math.floor(sub * TAX_RATES[code]) for code, sub in subtotal_by_code.items()
    }
    expected_tax = sum(tax_by_code.values())

    if invoice.tax_amount != expected_tax:
        messages.append(
            f"tax_amount mismatch: extracted={invoice.tax_amount}, "
            f"recalculated={expected_tax} (by code: {dict(tax_by_code)})"
        )

    expected_total = expected_subtotal + expected_tax
    if invoice.total_amount != expected_total:
        messages.append(
            f"total_amount mismatch: extracted={invoice.total_amount}, "
            f"recalculated={expected_total}"
        )

    ok = len(messages) == 0
    return VerificationResult(
        ok=ok,
        expected_subtotal=expected_subtotal,
        expected_tax=expected_tax,
        expected_total=expected_total,
        messages=messages,
    )
