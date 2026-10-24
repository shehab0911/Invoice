from datetime import date
from invoice_intake.models import ExtractedInvoice, LineItem, TaxCode
from invoice_intake.verifier import verify

def test_simple_10pct():
    inv = ExtractedInvoice(
        source_file="t.pdf",
        partner_name="test",
        invoice_number="X",
        issue_date=date(2026,1,1),
        due_date=date(2026,2,1),
        lines=[LineItem(description="a", unit="式", amount=10000, tax_code=TaxCode.T10)],
        subtotal=10000,
        tax_amount=1000,
        total_amount=11000,
    )
    assert verify(inv).ok

def test_mismatch():
    inv = ExtractedInvoice(
        source_file="t.pdf",
        partner_name="test",
        invoice_number="X",
        issue_date=date(2026,1,1),
        due_date=date(2026,2,1),
        lines=[LineItem(description="a", unit="式", amount=10000, tax_code=TaxCode.T10)],
        subtotal=10000,
        tax_amount=1000,
        total_amount=11001,
    )
    r = verify(inv)
    assert not r.ok
    assert r.expected_total == 11000
