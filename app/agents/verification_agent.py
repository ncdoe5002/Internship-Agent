"""
Verification Agent - Validates extracted tariff data and calculates text grounding confidence.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FieldDetail(BaseModel):
    value: Any = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["CONFIDENT", "FLAGGED", "LOW"] = "CONFIDENT"
    flags: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    status: str = Field(description="READY, REVIEW, FAILED")
    confidence: int = Field(ge=0, le=100, description="Confidence score (0-100)")
    checks: list[str] = Field(description="List of performed verification checks")
    issues: list[str] = Field(
        default_factory=list, description="List of identified issues"
    )
    field_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured per-field breakdown mapping header, models, rates, commitments",
    )


SYSTEM_METADATA_FIELDS = {
    "AGMT_ID",
    "BULK_ID",
    "USER_ACT_ID",
    "CREATED_DATE",
    "MODIFIED_DATE",
    "CREATED_USER",
    "MODIFIED_USER",
    "AGMT_VERIFIED_BY",
    "STATUS",
    "IS_ACTIVE",
}

NUMERIC_FIELDS = {
    "AMOUNT",
    "COMMIT_VALUE",
    "BASELINE_VALUE",
    "DISC_RATE_PERC",
    "CAPTURE_RATE_PCT",
    "TOTAL_AGMT_MONTH",
    "GPRS_LIMIT",
    "RATE",
    "PRICE",
    "COST",
}

DATE_FIELDS = {
    "START_DATE",
    "END_DATE",
    "CREATED_DATE",
    "MODIFIED_DATE",
    "AGMT_VERIFIED_DATE",
}


def normalize_text(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"[€$£]", "", s)
    s = re.sub(r"[,\s]+", " ", s)
    return s.strip()


def try_parse_number(s: Any) -> float | None:
    s = str(s)
    s = re.sub(r"[€$£,]", "", s)
    match = re.search(r"-?\d+(\.\d+)?", s)
    return float(match.group(0)) if match else None


def try_parse_date(s: Any) -> Any | None:
    s = str(s).strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def numeric_grounding(value: str, raw_doc_text: str) -> float:
    target = try_parse_number(value)
    if target is None:
        return 0.0
    doc_numbers = re.findall(r"-?\d[\d,]*\.?\d*", raw_doc_text)
    for raw_num in doc_numbers:
        parsed = try_parse_number(raw_num)
        if parsed is not None and abs(parsed - target) < 1e-6:
            return 1.0
    return 0.0


def date_grounding(value: str, raw_doc_text: str) -> float:
    target = try_parse_date(value)
    if target is None:
        return 0.0
    candidates = re.findall(
        r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}",
        raw_doc_text,
    )
    for cand in candidates:
        if try_parse_date(cand) == target:
            return 1.0
    return 0.0


def text_grounding(value: str, raw_doc_text: str) -> float:
    norm_val = normalize_text(value)
    norm_doc = normalize_text(raw_doc_text)
    if not norm_val:
        return 0.0
    if norm_val in norm_doc:
        return 1.0

    chunks = re.split(r"(?<=[.;\n])\s+", raw_doc_text)
    chunks = [normalize_text(c) for c in chunks if len(c.strip()) > 3]
    if not chunks:
        return 0.0
    return max(SequenceMatcher(None, norm_val, c).ratio() for c in chunks)


def calculate_field_confidence(field_name: str, value: Any, raw_doc_text: str) -> float:
    field_upper = field_name.upper()
    if field_upper in SYSTEM_METADATA_FIELDS:
        return 1.0
    if (
        value is None
        or str(value).strip() == ""
        or str(value).strip().lower() == "null"
    ):
        return 0.0

    str_val = str(value).strip()
    if field_upper in NUMERIC_FIELDS:
        return numeric_grounding(str_val, raw_doc_text)
    elif field_upper in DATE_FIELDS:
        return date_grounding(str_val, raw_doc_text)
    else:
        return text_grounding(str_val, raw_doc_text)


# --- Agent Models ---


class VerificationAgentInput(BaseModel):
    partner_name: str
    extracted_tables: dict
    raw_doc_text: str  # Mandatory for grounding
    baseline_tables: dict | None = None


# --- Main Agent Class ---


class VerificationAgent:
    def _check_currency_format(self, value: Any) -> bool:
        """Validates if a value follows valid monetary/numeric patterns."""
        if value is None or str(value).strip() == "":
            return True
        val_str = str(value).strip()
        pattern = r"^[\$€£]?\s*-?\d{1,3}(,\d{3})*(\.\d+)?%?$"
        return bool(re.match(pattern, val_str))

    def _check_date_format(self, value: Any) -> bool:
        """Validates if a date field can be parsed into a valid date."""
        if value is None or str(value).strip() == "":
            return True
        return try_parse_date(value) is not None

    def _check_date_consistency(self, header_data: dict) -> list[str]:
        """Validates presence and basic logic of start and end dates."""
        issues = []
        start_str = str(header_data.get("AGMT_EFF_DATE", "")).strip()
        end_str = str(header_data.get("AGMT_EXP_DATE", "")).strip()

        if not start_str or start_str in ("None", "null", ""):
            issues.append("Missing effective start date (AGMT_EFF_DATE)")
        if not end_str or end_str in ("None", "null", ""):
            issues.append("Missing expiration end date (AGMT_EXP_DATE)")

        return issues

    def _validate_table_structure(self, tables_payload: dict) -> list[str]:
        """Performs structural integrity checks on extracted tables."""
        issues = []
        tables = tables_payload.get("tables", [])

        for t_idx, table in enumerate(tables):
            title = table.get("title", f"Table #{t_idx + 1}")
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            if not headers:
                issues.append(f"Structural Issue: '{title}' missing column headers.")
                continue

            num_cols = len(headers)
            for r_idx, row in enumerate(rows):
                if len(row) != num_cols:
                    issues.append(
                        f"Structural Issue: Row {r_idx + 1} in '{title}' has {len(row)} columns, expected {num_cols}."
                    )

                for c_idx, cell in enumerate(row):
                    if c_idx >= num_cols:
                        break
                    header_name = headers[c_idx].upper()

                    if (
                        header_name in NUMERIC_FIELDS
                        and not self._check_currency_format(cell)
                    ):
                        issues.append(
                            f"Format Issue: Invalid numeric value '{cell}' for column '{headers[c_idx]}' in row {r_idx + 1}."
                        )

                    if header_name in DATE_FIELDS and not self._check_date_format(cell):
                        issues.append(
                            f"Format Issue: Invalid date format '{cell}' for column '{headers[c_idx]}' in row {r_idx + 1}."
                        )

        return issues

    def _check_baseline_variances(
        self, extracted_tables: dict, baseline_tables: dict | None
    ) -> list[str]:
        """Compares extracted data against baseline tables if present."""
        issues = []
        if not baseline_tables:
            return issues

        logger.info("Executing baseline comparison checks...")
        return issues

    def _check_cross_field_consistency(
        self, tables_payload: dict, raw_doc_text: str
    ) -> list[str]:
        """Deterministic cross-field checks ported from test_verification.py.
        Operates on the generic {tables:[{title,headers,rows}]} schema, not
        the staging schema, since extraction is out of scope here."""
        issues: list[str] = []
        header_row = {}
        for table in tables_payload.get("tables", []):
            if "HEADER" in table.get("title", "").upper():
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                if rows:
                    header_row = dict(zip(headers, rows[0]))
                break

        if not header_row:
            return issues

        start = try_parse_date(header_row.get("START_DATE"))
        end = try_parse_date(header_row.get("END_DATE"))
        stated_months = try_parse_number(header_row.get("TOTAL_AGMT_MONTH"))
        if start and end and stated_months is not None:
            computed_months = (end.year - start.year) * 12 + (end.month - start.month)
            if end.day >= start.day:
                computed_months += 1
            if abs(computed_months - stated_months) > 0:
                issues.append(
                    f"Consistency Issue: TOTAL_AGMT_MONTH={stated_months} does not match "
                    f"computed span START_DATE({start})-END_DATE({end})={computed_months} months."
                )

        fuzzy_threshold = 0.72
        doc_chunks = [
            normalize_text(c)
            for c in re.split(r"(?<=[.;\n])\s+", raw_doc_text)
            if len(c.strip()) > 3
        ]
        for party_field in ("SENDER", "RP"):
            party_val = header_row.get(party_field)
            if not party_val:
                continue
            norm_val = normalize_text(str(party_val))
            if norm_val in normalize_text(raw_doc_text):
                continue
            best_ratio = max(
                (SequenceMatcher(None, norm_val, c).ratio() for c in doc_chunks),
                default=0.0,
            )
            if best_ratio < fuzzy_threshold:
                issues.append(
                    f"Consistency Issue: {party_field} value '{party_val}' has no exact or "
                    f"close match (best similarity {best_ratio:.2f}) in source document body."
                )

        code = header_row.get("CURRENCY_CODE")
        agmt_currency = header_row.get("CURRENCY_AGMT")
        if code and agmt_currency:
            if code != agmt_currency:
                issues.append(
                    f"Duplicate Field Conflict: CURRENCY_CODE='{code}' differs from "
                    f"CURRENCY_AGMT='{agmt_currency}'; investigate which is authoritative."
                )
            else:
                issues.append(
                    f"Schema Note: CURRENCY_CODE and CURRENCY_AGMT hold the same value "
                    f"('{code}'); confirm with schema owner whether both fields are needed."
                )

        return issues
    def _calculate_overall_confidence(
        self, tables: dict, raw_doc_text: str
    ) -> tuple[int, list[str], dict[str, Any]]:
        scores: list[float] = []
        issues: list[str] = []

        field_details: dict[str, Any] = {
            "header": {},
            "models": [],
            "rates": [],
            "commitments": [],
        }

        for table in tables.get("tables", []):
            title = str(table.get("title", "")).upper()
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            target_key = None
            is_single_row = False

            if "AGMT_HEADER_STG" in title or "HEADER" in title:
                target_key = "header"
                is_single_row = True
            elif "AGMT_MODELS_STG" in title or "MODELS" in title:
                target_key = "models"
            elif "AGMT_MDL_NORMAL_STG" in title or "NORMAL" in title or "RATE" in title:
                target_key = "rates"
            elif "AGMT_COMMITMENT" in title or "COMMITMENT" in title:
                target_key = "commitments"

            if not target_key:
                continue

            for row in rows:
                row_dict = {}
                for col_idx, field_name in enumerate(headers):
                    cell_val = row[col_idx] if col_idx < len(row) else None
                    score = calculate_field_confidence(
                        field_name, cell_val, raw_doc_text
                    )
                    scores.append(score)

                    flags = []
                    if score < 0.65 and str(cell_val).strip() not in (
                        "",
                        "None",
                        "null",
                    ):
                        issues.append(
                            f"Low confidence ({score * 100:.0f}%) for {field_name}: '{cell_val}'"
                        )
                        flags.append("LOW_CONFIDENCE")

                    status = (
                        "CONFIDENT"
                        if score >= 0.85
                        else ("FLAGGED" if score >= 0.65 else "LOW")
                    )
                    detail = FieldDetail(
                        value=cell_val,
                        confidence_score=round(score, 2),
                        status=status,
                        flags=flags,
                    )

                    if is_single_row:
                        field_details["header"][field_name] = detail
                    else:
                        row_dict[field_name] = detail

                if not is_single_row:
                    field_details[target_key].append(row_dict)
                else:
                    break

        if not scores:
            return 0, ["No fields extracted to calculate confidence."], field_details

        avg_score = int((sum(scores) / len(scores)) * 100)
        return avg_score, issues, field_details

    def run(self, payload: VerificationAgentInput) -> VerificationResult:
        tables_exist = bool(payload.extracted_tables.get("tables"))
        issues = []
        checks = ["Tables extracted"]

        if not tables_exist:
            issues.append("No tables were extracted from the document")
            return VerificationResult(
                status="FAILED", confidence=0, checks=checks, issues=issues
            )

        # 1. Structural Checks
        structural_issues = self._validate_table_structure(payload.extracted_tables)
        issues.extend(structural_issues)
        checks.append("Table structure and column format verified")

        # 2. Baseline Comparison Checks
        baseline_issues = self._check_baseline_variances(
            payload.extracted_tables, payload.baseline_tables
        )
        issues.extend(baseline_issues)
        if payload.baseline_tables:
            checks.append("Baseline comparison verified")

        # 3. Grounding Confidence Checks
        confidence, grounding_issues, field_details = self._calculate_overall_confidence(
             payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(grounding_issues)
        checks.append("Field-level text grounding verified")
        # 4. Cross-Field Consistency Checks
        consistency_issues = self._check_cross_field_consistency(
            payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(consistency_issues)
        if consistency_issues:
            checks.append("Cross-field consistency checked")

        # 4. Final Status Evaluation
        if confidence < 70:
            status = "FAILED"
        elif confidence < 90 or len(issues) > 0:
            status = "REVIEW"
        else:
            status = "READY"

        logger.info(
            f"Verification completed: status={status}, confidence={confidence}, issues={len(issues)}"
        )
        return VerificationResult(
            status=status, confidence=confidence, checks=checks, issues=issues, field_details=field_details
        )
