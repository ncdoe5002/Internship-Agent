"""
Word document (.docx) extraction adapter.

Extracts tables and text from .docx files using python-docx.
Consumed by extraction_agent.py for Word document processing.

Dependency: python-docx>=1.1.2

Path: app/services/extraction/docx_adapter.py
      (Replaces existing empty file — was declared but never implemented.)
"""

import io
import logging

logger = logging.getLogger(__name__)


def extract_tables_from_docx(file_bytes: bytes) -> list[dict]:
    """
    Extract all tables from a .docx file.

    Iterates through every table in the document, treats the first row
    as headers and remaining rows as data. Skips tables with fewer than
    2 rows (header-only) and filters out completely empty rows.

    Args:
        file_bytes: Raw .docx file content as bytes.

    Returns:
        List of dicts, each containing:
            "title"   - Label string (e.g. "Table 1")
            "headers" - List of column header strings
            "rows"    - List of row data (each row is a list of strings)
        Returns empty list if no tables found or on failure.
    """
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not installed. Install with: pip install python-docx")
        return []

    tables_found = []

    try:
        doc = Document(io.BytesIO(file_bytes))

        for table_idx, table in enumerate(doc.tables):
            rows_data = []

            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows_data.append(cells)

            # Need at least header row + one data row
            if len(rows_data) < 2:
                continue

            headers = rows_data[0]
            data_rows = [
                row for row in rows_data[1:]
                if any(cell for cell in row)
            ]

            if data_rows:
                tables_found.append({
                    "title": f"Table {table_idx + 1}",
                    "headers": headers,
                    "rows": data_rows,
                })

    except Exception as e:
        logger.error(f"Word table extraction failed: {e}")
        return []

    logger.info(f"Extracted {len(tables_found)} tables from .docx")
    return tables_found


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract all paragraph text from a .docx file.

    Concatenates all non-empty paragraphs with newlines.
    Used as supplementary context for Gemini when tables alone
    don't capture all structured data (e.g. key-value pairs in prose).

    Args:
        file_bytes: Raw .docx file content as bytes.

    Returns:
        Full text content of the document, or "" on failure.
    """
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not installed.")
        return ""

    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        logger.info(f"Extracted {len(text)} chars from .docx paragraphs")
        return text
    except Exception as e:
        logger.error(f"Word text extraction failed: {e}")
        return ""
