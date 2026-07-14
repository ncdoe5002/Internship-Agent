"""Deterministic Excel extraction adapter.

This module converts spreadsheet sheets into the shared ExtractionResult schema
without any model calls. It preserves the existing extraction behavior used by
ExtractionAgent for `.xlsx` and `.xls` files.
"""

from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd

from app.schemas.extraction import ExtractionResult
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
    logger.info(f"Extracting the excel files for data. ")
    tables = []

    try:
        excel_files = BytesIO(
            file_bytes
        )  # To avoid storing the path of the file and using bytes to store and read the file in bytes no need to store

        try:
            xls_file = pd.ExcelFile(excel_files, engine="openpyxl")  # for files .xlsx
        except:
            xls_file = pd.ExcelFile(excel_files, engine="xlrd")
        sheet_count = 0
        row_count = 0
        for sheet_names in xls_file.sheet_names:
            if sheet_count >= MAX_TABLE_COUNT:
                logger.warning(
                    f"The total number of sheets has exceeded beyond the {MAX_TABLE_COUNT}"
                )
            excel_file_name = pd.read_excel(xls_file)
            if excel_file_name.empty():
                continue
            rows = []
            for _, row in excel_file_name.iterrows():
                if row_count >= MAX_ROW_COUNT:
                    logger.warning(
                        f"The rows in the file exceed beyond the limit {MAX_ROW_COUNT}"
                    )
                    break
                row_str = [str(v) if pd.notna(v) else "" for v in row]
                rows.append(row_str)
                total += 1
                # Storing the values in headers at index 0 and data in the rows below from index 1
                if rows:
                    headers = rows[0] if rows else []
                    data_rows = rows[1:] if len(rows) > 1 else []
                tables.append(
                    {
                        "title": sheet_names or f"sheet {sheet_count+1}",
                        "Headers": headers,
                        "rows": data_rows,
                    }
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
