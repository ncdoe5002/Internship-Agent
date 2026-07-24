"""
db_writer.py - Writes extracted tariff data to the staging DB tables.

Parses the tabular output from ExtractionAgent (a dict with a "tables" key)
and maps each table to the appropriate ORM model:

  "Agreement Header"       → AgmtHeaderStg
  "Agreement Models"       → AgmtModelsStg
  "Agreement Rate Details" → AgmtMdlNormalStg
  "Agreement Commitments"  → AgmtCommitment

Usage (inside a Celery task with app context):
    agmt_id = write_extraction_to_db(extraction_result_dict, document_id)
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models.agreement import (
    AgmtCommitment,
    AgmtHeaderStg,
    AgmtMdlNormalStg,
    AgmtModelsStg,
)

logger = logging.getLogger(__name__)

# Title strings returned by the agent (lowercase for comparison)
_HEADER_TITLES = {"agreement header"}
_MODELS_TITLES = {"agreement models"}
_RATES_TITLES = {"agreement rate details"}
_COMMITMENTS_TITLES = {"agreement commitments"}

# Maximum AGMT_ID column length (DB constraint)
_AGMT_ID_MAX = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_table(tables: list[dict], target_titles: set[str]) -> dict | None:
    """Return the first table whose title matches any of *target_titles* (case-insensitive)."""
    for t in tables:
        if t.get("title", "").strip().lower() in target_titles:
            return t
    return None


def _row_to_dict(headers: list[str], row: list) -> dict[str, str]:
    """Zip *headers* with *row* values into an uppercase-keyed dict."""
    result: dict[str, str] = {}
    for i, header in enumerate(headers):
        value = row[i] if i < len(row) else ""
        result[header.strip().upper()] = str(value).strip() if value is not None else ""
    return result


def _parse_bool(value: str) -> bool | None:
    if not value:
        return None
    return value.strip().upper() in ("Y", "YES", "TRUE", "1")


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    # Strip everything that is not a digit, dot, or leading minus
    cleaned = re.sub(r"[^\d.\-]", "", str(value).strip())
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _safe_str(value: str, max_len: int) -> str:
    return (value or "")[:max_len]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_extraction_to_db(extraction_result: dict, document_id: int) -> str:
    """Parse *extraction_result* and write records to the staging DB tables.

    Args:
        extraction_result: Dict produced by ``ExtractionAgent.run().model_dump()``.
                           Expected shape: ``{"tables": [...], "raw_text_summary": "..."}``.
        document_id:       The ``Document.id`` that owns these staging records.

    Returns:
        The ``AGMT_ID`` string used for all inserted staging records.
    """
    tables: list[dict] = extraction_result.get("tables", [])

    # ------------------------------------------------------------------
    # 1. Derive AGMT_ID from the extracted header (or fall back to doc id)
    # ------------------------------------------------------------------
    header_table = _find_table(tables, _HEADER_TITLES)
    header_data: dict[str, str] = {}

    if header_table and header_table.get("rows"):
        raw_headers = header_table.get("headers", [])
        raw_row = header_table["rows"][0]
        header_data = _row_to_dict(raw_headers, raw_row)

    extracted_agmt_id = header_data.get("AGMT_ID", "").strip()
    if extracted_agmt_id:
        # Prefix with doc id to guarantee uniqueness across uploads
        agmt_id = f"D{document_id}-{extracted_agmt_id}"[:_AGMT_ID_MAX]
    else:
        agmt_id = f"DOC-{document_id}"

    logger.info(f"db_writer: using AGMT_ID={agmt_id!r} for document_id={document_id}")

    # ------------------------------------------------------------------
    # 2. Wipe any previous staging data for this document's AGMT_ID
    # ------------------------------------------------------------------
    AgmtCommitment.query.filter_by(AGMT_ID=agmt_id).delete(synchronize_session=False)
    AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).delete(synchronize_session=False)
    AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).delete(synchronize_session=False)
    AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).delete(synchronize_session=False)
    db.session.flush()

    # ------------------------------------------------------------------
    # 3. Agreement Header
    # ------------------------------------------------------------------
    header_row = AgmtHeaderStg()
    header_row.AGMT_ID = agmt_id
    header_row.SENDER = _safe_str(header_data.get("SENDER", ""), 100)
    header_row.RP = _safe_str(header_data.get("RP", ""), 100)
    header_row.TAP_DIRECTION = _safe_str(header_data.get("TAP_DIRECTION", ""), 20)
    header_row.START_DATE = _parse_date(header_data.get("START_DATE", ""))
    header_row.END_DATE = _parse_date(header_data.get("END_DATE", ""))
    header_row.CURRENCY_CODE = _safe_str(header_data.get("CURRENCY_CODE", ""), 3)
    header_row.REMARKS = header_data.get("REMARKS", "")
    header_row.AUTO_RENEWAL = _parse_bool(header_data.get("AUTO_RENEWAL", ""))
    header_row.IS_GROUP_RP = _parse_bool(header_data.get("IS_GROUP_RP", ""))
    header_row.AGMT_STATUS = _safe_str(header_data.get("AGMT_STATUS", "DRAFT"), 20) or "DRAFT"
    header_row.AGMT_TYPE = _safe_str(header_data.get("AGMT_TYPE", ""), 20)
    header_row.CURRENCY_AGMT = _safe_str(header_data.get("CURRENCY_AGMT", ""), 3)
    header_row.EXCHANGE_RATE_TYPE = _safe_str(header_data.get("EXCHANGE_RATE_TYPE", ""), 20)
    header_row.CREATED_DATE = datetime.utcnow()
    db.session.add(header_row)
    db.session.flush()  # satisfy FK before inserting child rows

    # ------------------------------------------------------------------
    # 4. Agreement Models
    # ------------------------------------------------------------------
    models_table = _find_table(tables, _MODELS_TITLES)
    inserted_model_seqs: set[int] = set()

    if models_table and models_table.get("rows"):
        raw_headers = models_table.get("headers", [])
        for idx, raw_row in enumerate(models_table["rows"], start=1):
            row_data = _row_to_dict(raw_headers, raw_row)
            try:
                seq = int(row_data.get("MODEL_SEQ") or idx)
            except (ValueError, TypeError):
                seq = idx

            # Avoid duplicate (AGMT_ID, MODEL_SEQ) within a single document
            if seq in inserted_model_seqs:
                seq = max(inserted_model_seqs) + 1
            inserted_model_seqs.add(seq)

            model = AgmtModelsStg()
            model.AGMT_ID = agmt_id
            model.MODEL_SEQ = seq
            model.MODEL_TYPE = _safe_str(row_data.get("MODEL_TYPE", ""), 20)
            model.MODEL_NAME = _safe_str(row_data.get("MODEL_NAME", ""), 100)
            db.session.add(model)

    db.session.flush()

    # ------------------------------------------------------------------
    # 5. Agreement Rate Details
    # ------------------------------------------------------------------
    rates_table = _find_table(tables, _RATES_TITLES)

    if rates_table and rates_table.get("rows"):
        raw_headers = rates_table.get("headers", [])
        for raw_row in rates_table["rows"]:
            row_data = _row_to_dict(raw_headers, raw_row)
            rate = AgmtMdlNormalStg()
            rate.AGMT_ID = agmt_id
            rate.REC_TYPE = _safe_str(row_data.get("REC_TYPE", ""), 20)
            rate.ZONE_CODE = _safe_str(row_data.get("ZONE_CODE", ""), 20)
            rate.RATE_CURRENCY = _safe_str(row_data.get("RATE_CURRENCY", ""), 3)
            rate.PRA_RATE_TYPE = _safe_str(row_data.get("PRA_RATE_TYPE", ""), 20)
            rate.DISC_RATE_PERC = _parse_decimal(row_data.get("DISC_RATE_PERC", ""))
            rate.CHARGE_INCLUDE_TAX = _parse_bool(row_data.get("CHARGE_INCLUDE_TAX", ""))
            rate.CHARGE_FIELD = _parse_decimal(row_data.get("CHARGE_FIELD", ""))
            try:
                rate.MODEL_SEQ = int(row_data.get("MODEL_SEQ") or 1)
            except (ValueError, TypeError):
                rate.MODEL_SEQ = 1
            db.session.add(rate)

    # ------------------------------------------------------------------
    # 6. Agreement Commitments
    # ------------------------------------------------------------------
    commitments_table = _find_table(tables, _COMMITMENTS_TITLES)

    if commitments_table and commitments_table.get("rows"):
        raw_headers = commitments_table.get("headers", [])
        for raw_row in commitments_table["rows"]:
            row_data = _row_to_dict(raw_headers, raw_row)
            commitment = AgmtCommitment()
            commitment.AGMT_ID = agmt_id
            commitment.COMMITMENT_NAME = _safe_str(row_data.get("COMMITMENT_NAME", ""), 100)
            commitment.COMMITMENT_TYPE = _safe_str(row_data.get("COMMITMENT_TYPE", ""), 50)
            commitment.DIRECTION = _safe_str(row_data.get("DIRECTION", ""), 20)
            commitment.AMOUNT = _parse_decimal(row_data.get("AMOUNT", ""))
            commitment.CAPTURE_RATE_PCT = _parse_decimal(row_data.get("CAPTURE_RATE_PCT", ""))
            commitment.PARTY_FROM = _safe_str(row_data.get("PARTY_FROM", ""), 100)
            commitment.PARTY_TO = _safe_str(row_data.get("PARTY_TO", ""), 100)
            commitment.SOURCE_TYPE = _safe_str(row_data.get("SOURCE_TYPE", "TABLE"), 20) or "TABLE"
            commitment.CONFLICT_FLAG = _parse_bool(row_data.get("CONFLICT_FLAG", "N")) or False
            commitment.CONFLICT_NOTE = row_data.get("CONFLICT_NOTE", "")
            db.session.add(commitment)

    db.session.commit()
    logger.info(f"db_writer: staging records committed for AGMT_ID={agmt_id!r}")
    return agmt_id
