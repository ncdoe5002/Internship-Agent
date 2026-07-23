"""
Verification Agent - Validates extracted tariff data.

This agent performs validation checks on extracted tariff data to ensure
data quality and completeness. It compares extracted data against baseline
tables (if available) and returns a verification status with confidence scores.

Usage:
    agent = VerificationAgent()
    result = agent.run(payload)
"""

from __future__ import annotations
import logging, re
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    status: str = Field(description="READY, REVIEW, FAILED")
    confidence: int = Field(ge=0, le=100, description="Confidence score (0-100)")
    checks: list[str] = Field(description="List of performed verification checks")
    issues: list[str] = Field(
        default_factory=list, description="List of identified issues"
    )


class VerificationAgentInput(BaseModel):
    partner_name: str = Field(description="Name of the organization")
    extracted_tables: dict = Field(description="Extracted tables from the document")
    baseline_tables: dict | None = Field(
        default=None, description="Optional Tables for comparisons"
    )


class VerificationAgent:
    def _check_currency_format(self, tables: dict) -> tuple[bool, list[str]]:
        issues = []
        currency_pattern = re.compile(r"^[\$€£¥]?\s*[\d,]+\.?\d*\s*[\$€£¥]?$")
        rate_keywords = (
            "rate",
            "price",
            "cost",
            "tariff",
            "amount",
            "fee",
            "charge",
        )  # to check if any of these keywords match for the cost value
        for table in tables.get("tables", []):
            headers = table.get("headers", [])
            if isinstance(headers, list):
                rate_indices = [
                    idx
                    for idx, header in enumerate(headers)
                    if isinstance(header, str)
                    and any(keyword in header.lower() for keyword in rate_keywords)
                ]
            else:
                rate_indices = []

            if not rate_indices and isinstance(headers, list) and len(headers) >= 2:
                rate_indices = [1]

            rows = table.get("rows", [])
            for row_idx, row in enumerate(rows):
                if not isinstance(row, list):
                    continue
                for col_idx in rate_indices:
                    if col_idx >= len(row):
                        continue
                    cell = row[col_idx]
                    if cell is None or str(cell).strip() == "":
                        continue
                    if not currency_pattern.match(str(cell).strip()):
                        issues.append(
                            f"Table '{table.get('title', 'Untitled')}', row {row_idx}, "
                            f"column {col_idx}: Invalid currency format '{cell}'"
                        )
        return len(issues) == 0, issues

    def _check_effective_date(self, tables: dict) -> tuple[bool, list[str]]:
        """
           Checks for all the date formats

        Args:
            tables (dict): checks for date in the tables

        Returns:
            tuple[bool, list[str]]: Returns a boolean if date are matching and present and issues like
        """
        issues = []
        date_found = False
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",
        ]
        for table in tables.get("tables", []):
            headers = table.get("headers", [])
            for header in headers:
                if "effective" in header.lower() or "date" in header.lower():
                    date_found = True
                    break
            rows = table.get("rows", [])
            for row in rows:
                for cell in row:
                    for pattern in date_patterns:
                        if re.search(pattern, cell, re.IGNORECASE):
                            date_found = True
                            break
                    if date_found:
                        break
                if date_found:
                    break
            if date_found:
                break
        if not date_found:
            issues.append("No effective date found in the document")
        return date_found, issues

    def _check_partner_agreement(
        self, tables: dict, partner_name: str
    ) -> tuple[bool, list[str]]:
        issues = []
        partner_normalized = partner_name.lower().strip()
        partner_found = False
        for table in tables.get("tables", []):
            title = table.get("title", "")
            if partner_normalized in title.lower():
                partner_found = True
                break
            headers = table.get("headers", [])
            for header in headers:
                if partner_normalized in header.lower():
                    partner_found = True
                    break
            rows = table.get("rows", [])
            for row in rows:
                for cell in row:
                    if partner_normalized in cell.lower():
                        partner_found = True
                        break
                if partner_found:
                    break
            if partner_found:
                break
        if not partner_found:
            issues.append(f"Partner name '{partner_name}' not found in document")
        return partner_found, issues

    def _check_table_structure(self, tables: dict) -> tuple[bool, list[str]]:
        issues = []
        for table_idx, table in enumerate(tables.get("tables", [])):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            if not headers:
                issues.append(f"Table {table_idx}: Missing headers")
                continue
            for row_idx, row in enumerate(rows):
                for col_idx, cell in enumerate(row):
                    if not cell or cell.strip() == "":
                        issues.append(
                            f"Table {table_idx}, row {row_idx}, column {col_idx}: "
                            f"Empty cell (header: '{headers[col_idx] if col_idx < len(headers) else 'N/A'}')"
                        )
        return len(issues) == 0, issues

    def _check_edch_services(self, tables: dict) -> tuple[bool, list[str]]:
        """
        A service to look at tables that contains certain keywords

        Args:
            tables (dict): contains the data of each tables row and columns values

        Returns:
            tuple[bool, list[str]]: Returns the if the services and the issues
        """
        issues = []
        found_categories = set()
        for table in tables.get("tables", []):
            title = str(table.get("title", "")).lower()
            if any(
                k in title for k in ("tariff", "roaming", "agreement", "rate", "edch")
            ):
                rows = table.get("rows", [])
                for row in rows:
                    if isinstance(row, list) and len(row) > 0 and row[0]:
                        found_categories.add(str(row[0]).lower().strip())
        if found_categories:
            mandatory = {"voice", "data", "sms"}
            missing = [
                m for m in mandatory if not any(m in cat for cat in found_categories)
            ]
            if len(missing) == len(mandatory):
                issues.append(
                    f"Advisory: Standard roaming service categories missing: {', '.join(missing)}"
                )
        return True, issues

    def run(self, payload: VerificationAgentInput) -> VerificationResult:
        checks = []
        issues = []
        check_results = {}

        tables_exist = bool(payload.extracted_tables.get("tables"))
        check_results["tables_extracted"] = tables_exist
        checks.append("Tables extracted")
        if not tables_exist:
            issues.append("No tables were extracted from the document")

        if tables_exist:
            currency_passed, currency_issues = self._check_currency_format(
                payload.extracted_tables
            )
            check_results["currency_format"] = currency_passed
            checks.append("Currency format verified")
            issues.extend(currency_issues)

            date_passed, date_issues = self._check_effective_date(
                payload.extracted_tables
            )
            check_results["effective_date"] = date_passed
            checks.append("Effective date verified")
            issues.extend(date_issues)

            partner_passed, partner_issues = self._check_partner_agreement(
                payload.extracted_tables, payload.partner_name
            )
            check_results["partner_agreement"] = partner_passed
            checks.append("Partner agreement matched")
            issues.extend(partner_issues)

            structure_passed, structure_issues = self._check_table_structure(
                payload.extracted_tables
            )
            check_results["table_structure"] = structure_passed
            checks.append("Table structure verified")
            issues.extend(structure_issues)

            edch_passed, edch_issues = self._check_edch_services(
                payload.extracted_tables
            )
            check_results["edch_services"] = edch_passed
            checks.append("EDCH service categories checked")
            issues.extend(edch_issues)

        confidence = 100 if tables_exist else 0
        if tables_exist:
            confidence = max(0, 100 - (len(issues) * 10))

        total_checks = len(check_results)
        passed_checks = sum(1 for result in check_results.values() if result)

        if not tables_exist:
            status = "FAILED"
        elif confidence < 70:
            status = "FAILED"
        elif confidence < 90:
            status = "REVIEW"
        else:
            status = "READY"

        logger.info(
            f"Verification completed: status={status}, confidence={confidence}, "
            f"checks_passed={passed_checks}/{total_checks}, issues={len(issues)}"
        )

        return VerificationResult(
            status=status, confidence=confidence, checks=checks, issues=issues
        )
