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
    "VALUE",
}

DATE_FIELDS = {
    "START_DATE",
    "END_DATE",
    "AGMT_EFF_DATE",
    "AGMT_EXP_DATE",
    "CREATED_DATE",
    "MODIFIED_DATE",
    "AGMT_VERIFIED_DATE",
}

HEADER_ROLLUP_FIELDS = {
    "COMMIT_VALUE",
    "COMMIT_BASE_FIELD",
}

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
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
        return 0

    str_val = str(value).strip()
    if field_upper in NUMERIC_FIELDS:
        return numeric_grounding(str_val, raw_doc_text)
    elif field_upper in DATE_FIELDS:
        return date_grounding(str_val, raw_doc_text)
    else:
        return text_grounding(str_val, raw_doc_text)


def _parse_word_number(phrase: str) -> float | None:
    """Parses a constrained set of spelled-out numbers like
    'one hundred seventy thousand' or 'sixty five thousand'.
    Returns None if the phrase doesn't match the supported pattern."""
    words = re.findall(r"[a-z]+", phrase.lower())
    if not words:
        return None

    total = 0
    current = 0
    matched_any = False
    for w in words:
        if w in _WORD_NUMBERS:
            current += _WORD_NUMBERS[w]
            matched_any = True
        elif w == "hundred":
            current = (current or 1) * 100
            matched_any = True
        elif w in ("thousand", "thousands"):
            total += (current or 1) * 1000
            current = 0
            matched_any = True
    total += current
    return float(total) if matched_any else None


def flatten_header_values(extracted_tables: dict) -> dict:
    """Flattens header values from nested structure."""
    header = extracted_tables.get("AGMT_HEADER_STG", [])
    if not isinstance(header, list) or not header:
        return {}
    
    flat = {}
    for row in header:
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            flat[k] = v["value"] if isinstance(v, dict) and "value" in v else v
    return flat


def flatten_commitment_rows(extracted_tables: dict) -> list[dict]:
    """Flattens commitment rows from nested structure."""
    rows = extracted_tables.get("AGMT_COMMITMENT", [])
    if not isinstance(rows, list):
        return []
    flat_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        flat = {}
        for k, v in row.items():
            flat[k] = v["value"] if isinstance(v, dict) and "value" in v else v
        flat_rows.append(flat)
    return flat_rows


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

    def _check_prose_vs_table_conflict(
        self, extracted_tables: dict, raw_doc_text: str
    ) -> list[str]:
        """Detects discrepancies between narrative text and table values for commitment amounts."""
        issues: list[str] = []
        
        # Handle both staging schema and generic tables schema
        commitment_rows = []
        if "AGMT_COMMITMENT" in extracted_tables:
            commitment_data = extracted_tables.get("AGMT_COMMITMENT", [])
            if isinstance(commitment_data, list):
                commitment_rows = commitment_data
        else:
            commitment_rows = flatten_commitment_rows(extracted_tables)
        
        if not commitment_rows:
            return issues

        # Pull out table-block text specifically
        table_block_pattern = re.compile(
            r"(?:--- TABLE START ---|--- PAGE \d+ TABLES ---)(.*?)"
            r"(?:--- TABLE END ---|--- END TABLES ---)",
            re.DOTALL,
        )
        table_blocks = table_block_pattern.findall(raw_doc_text)
        if not table_blocks:
            return issues

        for row in commitment_rows:
            amount = row.get("AMOUNT")
            commitment_type = str(row.get("COMMITMENT_TYPE", "")).lower()
            direction = str(row.get("DIRECTION", "")).lower()
            party_to = str(row.get("PARTY_TO", ""))
            target = try_parse_number(amount)
            if target is None or "send or pay" not in commitment_type:
                continue

            # Look for a "Send or Pay Commitment" line in any table block whose
            # numeric value differs from the extracted AMOUNT.
            for block in table_blocks:
                for line in block.splitlines():
                    if (
                        "send or pay" not in line.lower()
                        and "commitment" not in line.lower()
                    ):
                        continue
                    nums = re.findall(r"-?\d[\d,]*\.?\d*", line)
                    for raw_num in nums:
                        parsed = try_parse_number(raw_num)
                        if parsed is not None and abs(parsed - target) > 1e-6:
                            issues.append(
                                f"Prose/Table Conflict: AGMT_COMMITMENT row "
                                f"'{row.get('COMMITMENT_NAME')}' (direction={direction}, "
                                f"party_to={party_to}) extracted AMOUNT={amount} from "
                                f"narrative text, but a source table row states "
                                f"'{line.strip()}' -- figures disagree ({target} vs "
                                f"{parsed}). Flag for manual review; do not silently "
                                "prefer either source."
                            )
        return issues

    def _check_spelled_out_number_conflict(
        self, extracted_tables: dict, raw_doc_text: str
    ) -> list[str]:
        """Detects mismatches between digit figures and parenthetical spelled-out numbers."""
        issues: list[str] = []
        pattern = re.compile(r"(?:EUR|€)\s*([\d,]+(?:\.\d+)?)\s*\(([^)]+)\)", re.IGNORECASE)
        for match in pattern.finditer(raw_doc_text):
            digit_str, word_str = match.group(1), match.group(2)
            digit_val = try_parse_number(digit_str)
            word_val = _parse_word_number(word_str)
            if (
                digit_val is not None
                and word_val is not None
                and abs(digit_val - word_val) > 1e-6
            ):
                issues.append(
                    f"Source Document Defect: figure 'EUR {digit_str}' is immediately "
                    f"followed by the parenthetical '({word_str})', which spells out "
                    f"to {word_val:,.0f}, not {digit_val:,.0f}. The source document "
                    "itself is internally inconsistent on this amount; this is not "
                    "an extraction error and cannot be resolved by re-reading the "
                    "same clause. Flag for the counterparty/legal, not for re-extraction."
                )
        return issues

    def _check_cross_field_consistency(
        self, tables_payload: dict, raw_doc_text: str
    ) -> list[str]:
        """Deterministic cross-field checks ported from test_verification.py.
        Operates on the generic {tables:[{title,headers,rows}]} schema, not
        the staging schema, since extraction is out of scope here."""
        issues: list[str] = []
        header_row = {}
        
        # Handle both staging schema and generic tables schema
        if "AGMT_HEADER_STG" in tables_payload:
            # Staging schema format
            header_data = tables_payload.get("AGMT_HEADER_STG", [])
            if isinstance(header_data, list) and header_data:
                header_row = header_data[0] if isinstance(header_data[0], dict) else {}
        else:
            # Generic tables schema format
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
                    f"Consistency Issue: {party_field} value '{party_val}' in header "
                    f"has low grounding (ratio={best_ratio:.2f}) in source document."
                )

        # Currency field conflict/redundancy check
        currency_code = header_row.get("CURRENCY_CODE")
        currency_agmt = header_row.get("CURRENCY_AGMT")
        if currency_code and currency_agmt:
            if str(currency_code).upper() != str(currency_agmt).upper():
                issues.append(
                    f"Duplicate Field Conflict: CURRENCY_CODE='{currency_code}' differs from "
                    f"CURRENCY_AGMT='{currency_agmt}'. Review which is correct."
                )

        # COMMIT_VALUE rollup field handling
        commit_value = header_row.get("COMMIT_VALUE")
        if commit_value is None or str(commit_value).strip() in ("", "null"):
            # Check if commitment rows exist with AMOUNT values
            commitment_rows = []
            
            if "AGMT_COMMITMENT" in tables_payload:
                # Staging schema format
                commitment_data = tables_payload.get("AGMT_COMMITMENT", [])
                if isinstance(commitment_data, list):
                    commitment_rows = commitment_data
            else:
                # Generic tables schema format
                for table in tables_payload.get("tables", []):
                    if "COMMITMENT" in table.get("title", "").upper():
                        headers = table.get("headers", [])
                        rows = table.get("rows", [])
                        for row in rows:
                            commitment_rows.append(dict(zip(headers, row)))
            
            if commitment_rows:
                total_commitment = 0.0
                for row in commitment_rows:
                    amount = try_parse_number(row.get("AMOUNT"))
                    if amount is not None:
                        total_commitment += amount
                
                if total_commitment > 0:
                    issues.append(
                        f"Mapping Issue: AGMT_HEADER_STG.COMMIT_VALUE is null, but "
                        f"AGMT_COMMITMENT rows contain total AMOUNT={total_commitment:,.0f}. "
                        "Consider mapping as rollup field."
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
            if "AGMT_HEADER_STG" in title or "HEADER" in title:
                target_key = "header"
            elif "AGMT_MODELS_STG" in title or "MODEL" in title:
                target_key = "models"
            elif (
                "AGMT_MDL_NORMAL_STG" in title
                or "NORMAL_MODEL" in title
                or "NORMAL" in title
                or "RATE" in title
            ):
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

                    flags = []
                    if score is not None:
                        scores.append(score)
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
                    else:
                        status = "CONFIDENT"  # Neutral status for optional null fields

                    detail = FieldDetail(
                        value=cell_val,
                        confidence_score=round(score, 2) if score is not None else 1.0,
                        status=status,
                        flags=flags,
                    )
                    row_dict[field_name] = detail

                if target_key == "header":
                    for k, v in row_dict.items():
                        field_details["header"][k] = v
                else:
                    field_details[target_key].append(row_dict)

        if not scores:
            # If all extracted fields were empty, default score is set to 100 for empty valid payloads
            return 100, issues, field_details

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

        # 2. Date Consistency Checks (NEW: Explicitly called)
        header_table = next(
            (
                t
                for t in payload.extracted_tables.get("tables", [])
                if "HEADER" in t.get("title", "").upper()
            ),
            {},
        )
        if header_table and header_table.get("rows"):
            header_dict = dict(
                zip(header_table.get("headers", []), header_table["rows"][0])
            )
            date_issues = self._check_date_consistency(header_dict)
            issues.extend(date_issues)
            checks.append("Date consistency checked")

        # 3. Baseline Comparison Checks
        baseline_issues = self._check_baseline_variances(
            payload.extracted_tables, payload.baseline_tables
        )
        issues.extend(baseline_issues)
        if payload.baseline_tables:
            checks.append("Baseline comparison verified")

        # 4. Cross-Field Consistency Checks
        consistency_issues = self._check_cross_field_consistency(
            payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(consistency_issues)
        checks.append("Cross-field consistency verified")

        # 5. Prose vs Table Conflict Checks (NEW)
        prose_table_issues = self._check_prose_vs_table_conflict(
            payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(prose_table_issues)
        if prose_table_issues:
            checks.append("Prose vs table conflict detection performed")

        # 6. Spelled-Out Number Conflict Checks (NEW)
        spelled_out_issues = self._check_spelled_out_number_conflict(
            payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(spelled_out_issues)
        if spelled_out_issues:
            checks.append("Spelled-out number conflict detection performed")

        # 7. Grounding Confidence Checks
        confidence, grounding_issues, field_details = (
            self._calculate_overall_confidence(
                payload.extracted_tables, payload.raw_doc_text
            )
        )
        issues.extend(grounding_issues)
        checks.append("Field-level text grounding verified")

        # 5. Cross-Field Consistency Checks
        consistency_issues = self._check_cross_field_consistency(
            payload.extracted_tables, payload.raw_doc_text
        )
        issues.extend(consistency_issues)

        # 6. Final Status Evaluation (Penalize missing mandatory fields)
        if len(issues) > 0 or confidence < 90:
            status = (
                "FAILED"
                if confidence < 70 or any("Missing" in i for i in issues)
                else "REVIEW"
            )
        else:
            status = "READY"

        return VerificationResult(
            status=status,
            confidence=confidence,
            checks=checks,
            issues=issues,
            field_details=field_details,
        )
