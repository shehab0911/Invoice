"""CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .api_client import AccountingClient
from .processor import InvoiceProcessor

console = Console()


@click.group()
def main():
    """Invoice Intake – automate reading & registration of supplier invoices."""
    pass


@main.command()
@click.option("--invoices-dir", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--api-url", default="http://localhost:8080", show_default=True)
@click.option("--api-key", default="demo-key-1234", show_default=True)
@click.option("--review-path", type=click.Path(path_type=Path), default="review_queue.json")
@click.option("--dry-run", is_flag=True, help="Extract & verify only, do not POST")
@click.option("--clear", is_flag=True, help="DELETE all existing invoices first")
def process(invoices_dir: Path, api_url: str, api_key: str, review_path: Path, dry_run: bool, clear: bool):
    """Process every invoice in a directory and register clean ones."""
    api = AccountingClient(api_url, api_key)
    try:
        health = api.health()
        console.print(f"API healthy – currently {health['data']['registered_invoices']} invoices registered")
    except Exception as e:
        console.print(f"[red]Cannot reach accounting API at {api_url}: {e}[/]")
        raise SystemExit(1)

    if clear:
        removed = api.clear()
        console.print(f"Cleared {removed} existing invoices")

    proc = InvoiceProcessor(api, review_path=review_path, auto_register=not dry_run)
    proc.process_dir(invoices_dir)


@main.command()
@click.option("--api-url", default="http://localhost:8080")
@click.option("--api-key", default="demo-key-1234")
def list_invoices(api_url: str, api_key: str):
    """List invoices currently registered in the accounting system."""
    api = AccountingClient(api_url, api_key)
    invs = api.list_invoices()
    if not invs:
        console.print("No invoices registered.")
        return
    for i in invs:
        console.print(
            f"{i['accounting_id']}  {i['partner_code']}  {i['invoice_number']}  "
            f"{i['issue_date']} → {i['due_date']}  total={i['total_amount']:,}"
        )


if __name__ == "__main__":
    main()
