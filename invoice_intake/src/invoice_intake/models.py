"""Canonical data models for invoice intake."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class TaxCode(str, Enum):
    T10 = "T10"
    T08 = "T08"


class LineItem(BaseModel):
    description: str
    quantity: Optional[int] = None
    unit: str = "式"
    unit_price: Optional[int] = None
    amount: int
    tax_code: TaxCode = TaxCode.T10

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> int:
        if isinstance(v, str):
            v = v.replace(",", "").replace("¥", "").replace("円", "").strip()
            if v.startswith("△") or v.startswith("▲"):
                v = "-" + v[1:]
            return int(float(v))
        return int(v)


class ExtractedInvoice(BaseModel):
    """Raw extraction result before partner matching / verification."""

    source_file: str
    partner_name: str
    partner_registration_no: Optional[str] = None
    invoice_number: str
    issue_date: date
    due_date: date
    currency: str = "JPY"
    lines: list[LineItem]
    subtotal: int
    tax_amount: int
    total_amount: int
    confidence: float = 1.0
    raw_notes: list[str] = Field(default_factory=list)

    @field_validator("issue_date", "due_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        return _normalize_japanese_date(str(v))


class MatchedInvoice(ExtractedInvoice):
    partner_code: str


class VerificationResult(BaseModel):
    ok: bool
    expected_subtotal: int
    expected_tax: int
    expected_total: int
    messages: list[str] = Field(default_factory=list)


class RegistrationResult(BaseModel):
    source_file: str
    success: bool
    accounting_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    needs_review: bool = False
    review_reason: Optional[str] = None


def _normalize_japanese_date(raw: str) -> date:
    """Handle YYYY-MM-DD, YYYY/MM/DD, YYYY年M月D日, 令和N年M月D日."""
    import re
    from datetime import date as dt_date

    raw = raw.strip().replace(" ", "")
    # ISO
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)
    if m:
        return dt_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # Japanese era
    m = re.match(r"^令和(\d+)年(\d+)月(\d+)日$", raw)
    if m:
        year = 2018 + int(m.group(1))  # Reiwa 1 = 2019
        return dt_date(year, int(m.group(2)), int(m.group(3)))

    m = re.match(r"^(\d{4})年(\d+)月(\d+)日$", raw)
    if m:
        return dt_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    raise ValueError(f"Unrecognised date format: {raw!r}")
