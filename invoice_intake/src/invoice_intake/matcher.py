"""Partner master matching."""

from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz, process

from .models import ExtractedInvoice, MatchedInvoice


class PartnerMatcher:
    def __init__(self, partners: list[dict]):
        self.partners = partners
        # Build lookup maps
        self.by_code = {p["partner_code"]: p for p in partners}
        self.by_reg = {p["registration_no"]: p for p in partners if p.get("registration_no")}
        self.name_to_code: dict[str, str] = {}
        for p in partners:
            self.name_to_code[p["name"]] = p["partner_code"]
            for alias in p.get("aliases", []):
                self.name_to_code[alias] = p["partner_code"]

    def match(self, inv: ExtractedInvoice) -> Optional[MatchedInvoice]:
        # 1. Exact registration number
        if inv.partner_registration_no and inv.partner_registration_no in self.by_reg:
            code = self.by_reg[inv.partner_registration_no]["partner_code"]
            return MatchedInvoice(**inv.model_dump(), partner_code=code)

        # 2. Exact name / alias
        if inv.partner_name in self.name_to_code:
            code = self.name_to_code[inv.partner_name]
            return MatchedInvoice(**inv.model_dump(), partner_code=code)

        # 3. Fuzzy name match (threshold 85)
        choices = list(self.name_to_code.keys())
        result = process.extractOne(
            inv.partner_name, choices, scorer=fuzz.token_sort_ratio, score_cutoff=85
        )
        if result:
            matched_name, score, _ = result
            code = self.name_to_code[matched_name]
            return MatchedInvoice(**inv.model_dump(), partner_code=code)

        return None
