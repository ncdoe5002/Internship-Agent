"""Deterministic Excel extraction adapter.

This module converts spreadsheet sheets into the shared ExtractionResult schema
without any model calls. It preserves the existing extraction behavior used by
ExtractionAgent for `.xlsx` and `.xls` files.
"""

from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd

from app.schemas.extraction import ExtractionResult, TableData
from app.services.storage import MAX_ROW_COUNT, MAX_TABLE_COUNT

logger = logging.getLogger(__name__)


def extract_from_excel(file_bytes: bytes) -> ExtractionResult:
    """Extract tabular data from an Excel workbook.

    The adapter reads each sheet as a table where the first non-empty row is
    treated as headers and all subsequent rows are treated as data rows. It
    enforces global extraction limits to bound workload and memory usage.

    Args:
        file_bytes: Raw bytes of an Excel workbook (`.xlsx` or `.xls`).

    Returns:
        ExtractionResult: Structured extraction output with one table per sheet.

    Raises:
        ValueError: If the workbook cannot be parsed with supported engines.
    """
    logger.info("Extracting data from Excel file")
    tables = []

    try:
        excel_file = BytesIO(file_bytes)

        try:
            xls = pd.ExcelFile(excel_file, engine="openpyxl")
        except:
            xls = pd.ExcelFile(excel_file, engine="xlrd")

        sheet_count = 0
        row_count = 0
        for sheet_name in xls.sheet_names:
            if sheet_count >= MAX_TABLE_COUNT:
                logger.warning(
                    f"Total number of sheets exceeded limit {MAX_TABLE_COUNT}"
                )
                break

            df = pd.read_excel(xls, sheet_name=sheet_name)
            if df.empty:
                continue

            rows = []
            for _, row in df.iterrows():
                if row_count >= MAX_ROW_COUNT:
                    logger.warning(
                        f"Row count exceeded limit {MAX_ROW_COUNT}"
                    )
                    break
                row_str = [str(v) if pd.notna(v) else "" for v in row]
                rows.append(row_str)
                row_count += 1

            if rows:
                headers = rows[0] if rows else []
                data_rows = rows[1:] if len(rows) > 1 else []
                tables.append(
                    TableData(
                        title=sheet_name or f"sheet {sheet_count + 1}",
                        headers=headers,
                        rows=data_rows,
                    )
                )
                sheet_count += 1

        logger.info("Extracted %s tables from Excel", len(tables))

    except Exception as e:
        logger.error("Excel extraction failed: %s", str(e))
        raise ValueError(f"Failed to extract from Excel file: {str(e)}") from e 

    return ExtractionResult(
        tables=tables,
        raw_text_summary=f"Extracted {len(tables)} tables from Excel file",
    )
