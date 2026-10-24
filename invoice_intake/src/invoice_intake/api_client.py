"""Thin client for the mock accounting API."""

from __future__ import annotations

from typing import Any, Optional

import requests

from .models import MatchedInvoice, RegistrationResult


class AccountingClient:
    def __init__(self, base_url: str = "http://localhost:8080", api_key: str = "demo-key-1234"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key, "Content-Type": "application/json"})

    def health(self) -> dict:
        r = self.session.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    def partners(self) -> list[dict]:
        r = self.session.get(f"{self.base_url}/partners")
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise RuntimeError(body.get("error"))
        return body["data"]["partners"]

    def register(self, inv: MatchedInvoice) -> RegistrationResult:
        payload = {
            "partner_code": inv.partner_code,
            "invoice_number": inv.invoice_number,
            "issue_date": inv.issue_date.isoformat(),
            "due_date": inv.due_date.isoformat(),
            "currency": inv.currency,
            "lines": [
                {
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "unit_price": line.unit_price,
                    "amount": line.amount,
                    "tax_code": line.tax_code.value,
                }
                for line in inv.lines
            ],
            "subtotal": inv.subtotal,
            "tax_amount": inv.tax_amount,
            "total_amount": inv.total_amount,
        }
        r = self.session.post(f"{self.base_url}/invoices", json=payload)
        body = r.json()
        if body.get("success"):
            return RegistrationResult(
                source_file=inv.source_file,
                success=True,
                accounting_id=body["data"]["accounting_id"],
            )
        err = body.get("error") or {}
        return RegistrationResult(
            source_file=inv.source_file,
            success=False,
            error_code=err.get("code"),
            error_message=err.get("message"),
            needs_review=True,
            review_reason=f"{err.get('code')}: {err.get('message')}",
        )

    def list_invoices(self) -> list[dict]:
        r = self.session.get(f"{self.base_url}/invoices")
        r.raise_for_status()
        return r.json()["data"]["invoices"]

    def clear(self) -> int:
        r = self.session.delete(f"{self.base_url}/invoices")
        r.raise_for_status()
        return r.json()["data"]["removed"]
