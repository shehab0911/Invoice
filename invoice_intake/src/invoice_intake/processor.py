"""End-to-end invoice processing pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .api_client import AccountingClient
from .extractor import extract
from .matcher import PartnerMatcher
from .models import RegistrationResult
from .verifier import verify

console = Console()


class InvoiceProcessor:
    def __init__(
        self,
        api: AccountingClient,
        review_path: Path = Path("review_queue.json"),
        auto_register: bool = True,
    ):
        self.api = api
        self.review_path = review_path
        self.auto_register = auto_register
        partners = api.partners()
        self.matcher = PartnerMatcher(partners)
        self.results: list[RegistrationResult] = []
        self.review_queue: list[dict] = []

    def process_file(self, path: Path) -> RegistrationResult:
        console.print(f"\n[bold]Processing[/] {path.name}")
        try:
            extracted = extract(path)
        except Exception as e:
            res = RegistrationResult(
                source_file=path.name,
                success=False,
                needs_review=True,
                review_reason=f"extraction_failed: {e}",
            )
            self.results.append(res)
            self.review_queue.append({"file": path.name, "reason": str(e)})
            return res

        # Low-confidence gate
        if extracted.confidence < 0.6:
            console.print(f"  [yellow]Low confidence ({extracted.confidence:.2f}) – queued for review[/]")
            res = RegistrationResult(
                source_file=path.name,
                success=False,
                needs_review=True,
                review_reason=f"low_confidence={extracted.confidence:.2f}",
            )
            self.results.append(res)
            self.review_queue.append({
                "file": path.name,
                "reason": "low_confidence",
                "confidence": extracted.confidence,
                "extracted": extracted.model_dump(mode="json"),
            })
            return res

        # Verify amounts
        v = verify(extracted)
        if not v.ok:
            console.print(f"  [yellow]Verification failed:[/] {v.messages}")
            # For invoice_09 we still try to register with corrected totals if desired;
            # here we flag for review and do not auto-correct.
            res = RegistrationResult(
                source_file=path.name,
                success=False,
                needs_review=True,
                review_reason="; ".join(v.messages),
            )
            self.results.append(res)
            self.review_queue.append(
                {
                    "file": path.name,
                    "reason": "amount_mismatch",
                    "messages": v.messages,
                    "extracted": extracted.model_dump(mode="json"),
                    "expected": {
                        "subtotal": v.expected_subtotal,
                        "tax": v.expected_tax,
                        "total": v.expected_total,
                    },
                }
            )
            return res

        # Match partner
        matched = self.matcher.match(extracted)
        if matched is None:
            console.print(f"  [red]Unknown partner:[/] {extracted.partner_name}")
            res = RegistrationResult(
                source_file=path.name,
                success=False,
                needs_review=True,
                review_reason=f"PARTNER_NOT_FOUND: {extracted.partner_name}",
            )
            self.results.append(res)
            self.review_queue.append(
                {
                    "file": path.name,
                    "reason": "unknown_partner",
                    "partner_name": extracted.partner_name,
                    "registration_no": extracted.partner_registration_no,
                    "extracted": extracted.model_dump(mode="json"),
                }
            )
            return res

        console.print(f"  Matched partner [cyan]{matched.partner_code}[/] ({matched.partner_name})")

        if not self.auto_register:
            res = RegistrationResult(
                source_file=path.name,
                success=False,
                needs_review=False,
                review_reason="dry-run",
            )
            self.results.append(res)
            return res

        # Register
        res = self.api.register(matched)
        if res.success:
            console.print(f"  [green]Registered[/] → {res.accounting_id}")
        else:
            console.print(f"  [red]API rejected[/] {res.error_code}: {res.error_message}")
            if res.error_code == "DUPLICATE_INVOICE":
                # Already known – not necessarily a review item
                res.needs_review = False
            else:
                self.review_queue.append(
                    {
                        "file": path.name,
                        "reason": res.error_code,
                        "message": res.error_message,
                        "extracted": matched.model_dump(mode="json"),
                    }
                )
        self.results.append(res)
        return res

    def process_dir(self, invoices_dir: Path) -> list[RegistrationResult]:
        files = sorted(
            list(invoices_dir.glob("*.pdf")) + list(invoices_dir.glob("*.jpg"))
        )
        for f in files:
            self.process_file(f)
        self._write_review_queue()
        self._print_summary()
        return self.results

    def _write_review_queue(self) -> None:
        if self.review_queue:
            self.review_path.write_text(
                json.dumps(self.review_queue, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            console.print(f"\n[yellow]Review queue written to {self.review_path}[/]")

    def _print_summary(self) -> None:
        table = Table(title="Processing Summary")
        table.add_column("File")
        table.add_column("Result")
        table.add_column("Detail")
        for r in self.results:
            status = "[green]OK[/]" if r.success else ("[yellow]REVIEW[/]" if r.needs_review else "[red]FAIL[/]")
            detail = r.accounting_id or r.error_code or r.review_reason or ""
            table.add_row(r.source_file, status, detail)
        console.print(table)
