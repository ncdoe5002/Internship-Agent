"""
PDF extraction adapter — reads PDF files and extracts text, tables, and page images.

Handles raw PDF processing using PyMuPDF. Does not interact with Gemini;
this is a preprocessing utility consumed by extraction_agent.py.

Dependency: PyMuPDF>=1.24.5 (imported as 'fitz')

Path: app/services/extraction/pdf_adapter.py
      (Replaces existing empty file — was declared but never implemented.)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract all readable text from a PDF.

    Iterates through each page, extracts text content, and concatenates
    with page markers. Returns empty string for scanned/image-only PDFs
    since those have no text layer.

    Args:
        pdf_bytes: Raw PDF file content as bytes.

    Returns:
        Concatenated text from all pages, or "" on failure.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed. Install with: pip install PyMuPDF")
        return ""

    text_parts = []

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")

            if page_text.strip():
                text_parts.append(
                    f"--- PAGE {page_num + 1} ---\n{page_text.strip()}"
                )

        doc.close()
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""

    full_text = "\n\n".join(text_parts)
    logger.info(f"Extracted {len(full_text)} chars from {len(text_parts)} pages")
    return full_text


def extract_tables_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Detect and extract tables from a PDF using PyMuPDF's built-in
    table detection (requires PyMuPDF >= 1.23.0).

    Scans each page for grid-based table structures. First row of
    each detected table is treated as headers; remaining rows as data.

    Args:
        pdf_bytes: Raw PDF file content as bytes.

    Returns:
        List of dicts, each containing:
            "title"   - Description string (e.g. "Table from Page 2, Table 1")
            "headers" - List of column header strings
            "rows"    - List of row data (each row is a list of strings)
            "page"    - Page number where the table was found
        Returns empty list if no tables detected or on failure.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed.")
        return []

    tables_found = []

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc[page_num]

            # find_tables() requires PyMuPDF >= 1.23.0
            if not hasattr(page, "find_tables"):
                logger.warning(
                    "PyMuPDF version does not support find_tables(). "
                    "Upgrade to >= 1.23.0 for table detection."
                )
                doc.close()
                return []

            tab_finder = page.find_tables()

            for table_idx, table in enumerate(tab_finder.tables):
                raw_data = table.extract()

                # Need at least header row + one data row
                if not raw_data or len(raw_data) < 2:
                    continue

                headers = [
                    str(cell).strip() if cell else ""
                    for cell in raw_data[0]
                ]

                rows = []
                for row in raw_data[1:]:
                    cleaned_row = [
                        str(cell).strip() if cell else ""
                        for cell in row
                    ]
                    # Skip completely empty rows
                    if any(cell for cell in cleaned_row):
                        rows.append(cleaned_row)

                if rows:
                    tables_found.append({
                        "title": f"Table from Page {page_num + 1}, Table {table_idx + 1}",
                        "headers": headers,
                        "rows": rows,
                        "page": page_num + 1,
                    })

        doc.close()
    except Exception as e:
        logger.error(f"PDF table extraction failed: {e}")
        return []

    logger.info(f"Detected {len(tables_found)} tables in PDF")
    return tables_found


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in the PDF, or 0 on failure."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def pdf_to_images(
    pdf_bytes: bytes,
    dpi: int = 200,
    max_pages: Optional[int] = None,
) -> list[bytes]:
    """
    Render PDF pages as PNG images.

    Used for scanned PDFs that have no text layer — the rendered images
    can be sent to Gemini's vision model for OCR-based extraction.

    Default DPI of 200 balances image quality against file size.
    Pages are capped at max_pages to stay within API token limits.

    Args:
        pdf_bytes:  Raw PDF file content.
        dpi:        Render resolution (72=screen, 200=default, 300=print).
        max_pages:  Maximum pages to render. None renders all pages.

    Returns:
        List of PNG byte arrays, one per rendered page.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed.")
        return []

    images = []

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_limit = max_pages or len(doc)

        for page_num in range(min(page_limit, len(doc))):
            page = doc[page_num]

            # Default PDF resolution is 72 DPI; scale accordingly
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            images.append(pix.tobytes("png"))

        doc.close()
    except Exception as e:
        logger.error(f"PDF to image conversion failed: {e}")
        return []

    logger.info(f"Rendered {len(images)} pages as PNG images")
    return images