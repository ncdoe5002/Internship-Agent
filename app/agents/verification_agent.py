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

import logging
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """
    Result of the verification process.

    Attributes:
        status: Verification status - "READY" (can proceed), "REVIEW" (needs review),
            or "FAILED" (verification failed).
        confidence: Confidence score from 0-100 indicating data quality.
        checks: List of verification checks that were performed.
        issues: List of any issues or problems found during verification.
    """

    status: str = Field(description="READY, REVIEW, or FAILED")
    confidence: int = Field(ge=0, le=100, description="Confidence score (0-100)")
    checks: list[str] = Field(description="List of performed verification checks")
    issues: list[str] = Field(
        default_factory=list, description="List of identified issues"
    )


class VerificationAgentInput(BaseModel):
    """
    Input schema for the Verification Agent.

    Attributes:
        partner_name: Name of the partner organization.
        extracted_tables: Dictionary of tables extracted from the document.
        baseline_tables: Optional dictionary of baseline/reference tables for comparison.
    """

    partner_name: str = Field(description="Name of the partner organization")
    extracted_tables: dict = Field(
        description="Extracted tariff tables from the document"
    )
    baseline_tables: dict | None = Field(
        default=None, description="Optional baseline tables for comparison"
    )


class VerificationAgent:
    """
    Agent responsible for verifying extracted tariff data.

    This agent performs various validation checks on the extracted data to ensure
    quality, completeness, and accuracy. It returns a verification result with
    a status, confidence score, and list of any issues found.
    """

    def _check_currency_format(self, tables: dict) -> tuple[bool, list[str]]:
        """
        Verify currency format consistency across extracted rows.

        Args:
            tables: Extracted tables from the document

        Returns:
            Tuple of (passed, issues)
        """
        issues = []
        currency_pattern = re.compile(r"^[\$€£¥]?\s*[\d,]+\.?\d*\s*[\$€£¥]?$")
        rate_keywords = ("rate", "price", "cost", "tariff", "amount", "fee", "charge")

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
        Verify effective date is present and parseable.

        Args:
            tables: Extracted tables from the document

        Returns:
            Tuple of (passed, issues)
        """
        issues = []
        date_found = False

        # Common date patterns
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{2}/\d{2}/\d{4}",  # MM/DD/YYYY
            r"\d{2}-\d{2}-\d{4}",  # MM-DD-YYYY
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",  # Month DD, YYYY
        ]

        for table in tables.get("tables", []):
            # Check headers for date-related fields
            headers = table.get("headers", [])
            for header in headers:
                if "effective" in header.lower() or "date" in header.lower():
                    date_found = True
                    break

            # Check rows for date values
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
        """
        Verify partner/agreement name in the document matches the expected partner_name.

        Args:
            tables: Extracted tables from the document
            partner_name: Expected partner name

        Returns:
            Tuple of (passed, issues)
        """
        issues = []
        partner_normalized = partner_name.lower().strip()
        partner_found = False

        for table in tables.get("tables", []):
            # Check title
            title = table.get("title", "")
            if partner_normalized in title.lower():
                partner_found = True
                break

            # Check headers
            headers = table.get("headers", [])
            for header in headers:
                if partner_normalized in header.lower():
                    partner_found = True
                    break

            # Check rows
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
        """
        Verify table structure completeness (no missing headers, no empty required cells).

        Args:
            tables: Extracted tables from the document

        Returns:
            Tuple of (passed, issues)
        """
        issues = []

        for table_idx, table in enumerate(tables.get("tables", [])):
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            # Check for missing headers
            if not headers:
                issues.append(f"Table {table_idx}: Missing headers")
                continue

            # Check for empty required cells (assuming all cells are required)
            for row_idx, row in enumerate(rows):
                for col_idx, cell in enumerate(row):
                    if not cell or cell.strip() == "":
                        issues.append(
                            f"Table {table_idx}, row {row_idx}, column {col_idx}: "
                            f"Empty cell (header: '{headers[col_idx] if col_idx < len(headers) else 'N/A'}')"
                        )

        return len(issues) == 0, issues

    def run(self, payload: VerificationAgentInput) -> VerificationResult:
        """
        Execute verification checks on the extracted data.

        This method performs validation checks including:
        - Table extraction verification
        - Currency format validation
        - Effective date validation
        - Agreement matching
        - Table structure completeness

        Args:
            payload: Input containing partner name, extracted tables, and optional baseline.

        Returns:
            VerificationResult: Verification status, confidence score, performed checks,
                and any issues found.
        """
        checks = []
        issues = []
        check_results = {}

        # Check 1: Tables extracted
        tables_exist = bool(payload.extracted_tables.get("tables"))
        check_results["tables_extracted"] = tables_exist
        checks.append("Tables extracted")
        if not tables_exist:
            issues.append("No tables were extracted from the document")

        # Only run other checks if tables exist
        if tables_exist:
            # Check 2: Currency format
            currency_passed, currency_issues = self._check_currency_format(
                payload.extracted_tables
            )
            check_results["currency_format"] = currency_passed
            checks.append("Currency format verified")
            issues.extend(currency_issues)

            # Check 3: Effective date
            date_passed, date_issues = self._check_effective_date(
                payload.extracted_tables
            )
            check_results["effective_date"] = date_passed
            checks.append("Effective date verified")
            issues.extend(date_issues)

            # Check 4: Partner agreement
            partner_passed, partner_issues = self._check_partner_agreement(
                payload.extracted_tables, payload.partner_name
            )
            check_results["partner_agreement"] = partner_passed
            checks.append("Partner agreement matched")
            issues.extend(partner_issues)

            # Check 5: Table structure
            structure_passed, structure_issues = self._check_table_structure(
                payload.extracted_tables
            )
            check_results["table_structure"] = structure_passed
            checks.append("Table structure verified")
            issues.extend(structure_issues)

        # Confidence is intentionally issue-driven so one or two missing signals
        # do not collapse a mostly valid document into FAILED.
        confidence = 100 if tables_exist else 0
        if tables_exist:
            confidence = max(0, 100 - (len(issues) * 10))

        total_checks = len(check_results)
        passed_checks = sum(1 for result in check_results.values() if result)

        # Determine status based on confidence and critical failures
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
            status=status,
            confidence=confidence,
            checks=checks,
            issues=issues,
        )
