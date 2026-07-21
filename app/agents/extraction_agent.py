"""
Extraction Agent — sends documents to Gemini for structured data extraction.

Supports PDF and Word (.docx) documents.

PDF strategy (3-tier fallback):
    1. Direct PDF upload to Gemini (native PDF support)
    2. PDF-to-image conversion + Gemini vision (handles scanned documents)
    3. Text extraction via PyMuPDF + Gemini text input (last resort)

Word strategy (2-tier):
    1. Direct table extraction via python-docx (no AI needed)
    2. Text extraction + Gemini for non-table structured data

Returns ExtractionResult containing parsed table data matching
the agreement staging table schemas.

Dependencies:
    google-generativeai   (Gemini SDK)
    PyMuPDF >= 1.24.5     (PDF processing)
    python-docx >= 1.1.2  (Word processing)

Path: app/agents/extraction_agent.py
      (Replaces existing file — _extract_from_pdf() and _extract_from_word()
      were called in run() but never implemented, causing AttributeError
      on any document upload.)
"""

import json
import base64
import logging
from typing import Optional

from pydantic import BaseModel

from app.schemas.extraction import ExtractionResult, TableData
from app.agents.prompts import (
    ROAMING_AGREEMENT_PROMPT,
    GENERIC_TABLE_EXTRACTION_PROMPT,
)
from app.services.extraction.pdf_adapter import (
    extract_text_from_pdf,
    pdf_to_images,
)
from app.services.extraction.docx_adapter import (
    extract_tables_from_docx,
    extract_text_from_docx,
)

logger = logging.getLogger(__name__)


class ExtractionPayload(BaseModel):
    """Input payload for the extraction agent."""
    document_bytes: bytes
    document_type: str             # "pdf", "docx", "xlsx"
    filename: str = ""
    use_telecom_prompt: bool = True


class ExtractionAgent:
    """
    Document extraction agent. Accepts file bytes, sends them to Gemini,
    and returns structured table data as ExtractionResult.

    Usage:
        agent = ExtractionAgent(model=gemini_model)
        payload = ExtractionPayload(
            document_bytes=file_bytes,
            document_type="pdf",
            filename="agreement.pdf",
        )
        result = agent.run(payload)
    """

    def __init__(self, model):
        """
        Args:
            model: LangChain ChatGoogleGenerativeAI instance
                   (created in app/services/gemini.py).
        """
        self.model = model

    def run(self, payload: ExtractionPayload) -> ExtractionResult:
        """
        Entry point — routes to the appropriate extractor based on file type.
        Called by the Orchestrator's extraction_node.
        """
        doc_type = payload.document_type.lower()
        logger.info(f"ExtractionAgent processing: {payload.filename} ({doc_type})")

        if doc_type == "pdf":
            return self._extract_from_pdf(payload)

        elif doc_type in ("docx", "doc"):
            return self._extract_from_word(payload)

        elif doc_type in ("xlsx", "xls", "csv"):
            # Handled by excel_adapter.py; should not route through here
            logger.error("Excel files should use excel_adapter.py directly")
            return ExtractionResult(tables=[])

        else:
            logger.error(f"Unsupported document type: {doc_type}")
            return ExtractionResult(tables=[])

    # ═══════════════════════════════════════════════════════════════════
    # PDF EXTRACTION — 3-tier fallback
    # ═══════════════════════════════════════════════════════════════════

    def _extract_from_pdf(self, payload: ExtractionPayload) -> ExtractionResult:
        """
        Extract structured data from a PDF using Gemini.

        Attempts three strategies in sequence, falling through on failure:
            1. Direct PDF → Gemini (fastest, best accuracy)
            2. PDF → PNG images → Gemini vision (handles scanned docs)
            3. PDF → extracted text → Gemini text input (fallback)
        """
        pdf_bytes = payload.document_bytes
        prompt = (
            ROAMING_AGREEMENT_PROMPT
            if payload.use_telecom_prompt
            else GENERIC_TABLE_EXTRACTION_PROMPT
        )

        # Attempt 1: Direct PDF upload
        logger.info("PDF extraction: attempting direct Gemini upload")
        try:
            result = self._send_pdf_to_gemini(pdf_bytes, prompt)
            if result and result.tables:
                logger.info(f"Direct upload succeeded: {len(result.tables)} tables")
                return result
        except Exception as e:
            logger.warning(f"Direct upload failed: {e}")

        # Attempt 2: Image-based extraction
        logger.info("PDF extraction: attempting image-based approach")
        try:
            result = self._send_pdf_as_images(pdf_bytes, prompt)
            if result and result.tables:
                logger.info(f"Image extraction succeeded: {len(result.tables)} tables")
                return result
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        # Attempt 3: Text-based extraction
        logger.info("PDF extraction: attempting text-based approach")
        try:
            result = self._extract_via_text(
                payload.document_bytes, payload.use_telecom_prompt
            )
            if result and result.tables:
                logger.info(f"Text extraction succeeded: {len(result.tables)} tables")
                return result
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")

        logger.error("All PDF extraction attempts failed")
        return ExtractionResult(tables=[])

    # ── PDF Attempt 1: Direct upload ────────────────────────────────────

    def _send_pdf_to_gemini(
        self, pdf_bytes: bytes, prompt: str
    ) -> Optional[ExtractionResult]:
        """
        Send raw PDF to Gemini as multimodal input (base64-encoded).

        Uses the raw google-generativeai SDK instead of the LangChain wrapper
        because LangChain's ChatGoogleGenerativeAI does not reliably handle
        binary file uploads.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            logger.error("google-generativeai package not installed")
            return None

        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        content_parts = [
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": pdf_b64,
                }
            },
            {"text": prompt},
        ]

        try:
            model_name = getattr(self.model, "model", "gemini-1.5-flash")
            if model_name.startswith("models/"):
                model_name = model_name.replace("models/", "")

            genai_model = genai.GenerativeModel(model_name=model_name)

            response = genai_model.generate_content(
                content_parts,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )

            return self._extract_json_from_response(response.text)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    # ── PDF Attempt 2: Image-based ──────────────────────────────────────

    def _send_pdf_as_images(
        self, pdf_bytes: bytes, prompt: str
    ) -> Optional[ExtractionResult]:
        """
        Convert PDF pages to PNG images and send to Gemini vision.
        Handles scanned PDFs with no text layer.
        Capped at 20 pages to stay within API token limits.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            return None

        page_images = pdf_to_images(pdf_bytes, dpi=200, max_pages=20)

        if not page_images:
            logger.warning("No images rendered from PDF")
            return None

        content_parts = []
        for img_bytes in page_images:
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": img_b64,
                }
            })

        content_parts.append({
            "text": (
                f"This document has {len(page_images)} pages shown above. "
                f"{prompt}"
            )
        })

        try:
            model_name = getattr(self.model, "model", "gemini-1.5-flash")
            if model_name.startswith("models/"):
                model_name = model_name.replace("models/", "")

            genai_model = genai.GenerativeModel(model_name=model_name)

            response = genai_model.generate_content(
                content_parts,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )

            return self._extract_json_from_response(response.text)

        except Exception as e:
            logger.error(f"Image-based Gemini call failed: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════
    # WORD (.docx) EXTRACTION — 2-tier strategy
    # ═══════════════════════════════════════════════════════════════════

    def _extract_from_word(self, payload: ExtractionPayload) -> ExtractionResult:
        """
        Extract structured data from a Word document.

        Strategy:
            1. Extract tables directly via python-docx (fast, no API call)
            2. Extract full text and send to Gemini for non-table data
               (key-value pairs in paragraphs, unstructured rate info, etc.)
            3. Merge results, deduplicating by table title
        """
        docx_bytes = payload.document_bytes

        # ── Step 1: Direct table extraction via python-docx ─────────
        direct_tables = extract_tables_from_docx(docx_bytes)

        tables = []
        for dt in direct_tables:
            tables.append(
                TableData(
                    title=dt["title"],
                    headers=dt["headers"],
                    rows=dt["rows"],
                )
            )

        logger.info(f"python-docx extracted {len(tables)} tables directly")

        # ── Step 2: Send text to Gemini for additional structured data
        text = extract_text_from_docx(docx_bytes)

        if text.strip():
            gemini_result = self._extract_via_text(
                docx_bytes, payload.use_telecom_prompt, text_override=text
            )

            if gemini_result and gemini_result.tables:
                # Merge: add Gemini tables that aren't duplicates
                existing_titles = {t.title for t in tables}
                for gt in gemini_result.tables:
                    if gt.title not in existing_titles:
                        tables.append(gt)

                logger.info(
                    f"Gemini added {len(gemini_result.tables)} additional tables"
                )

        logger.info(f"Word extraction complete: {len(tables)} tables total")
        return ExtractionResult(
            tables=tables,
            raw_text_summary=text[:2000] if text else None,
        )

    # ═══════════════════════════════════════════════════════════════════
    # SHARED: Text-based Gemini extraction (used by both PDF and Word)
    # ═══════════════════════════════════════════════════════════════════

    def _extract_via_text(
        self,
        document_bytes: bytes,
        use_telecom_prompt: bool,
        text_override: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Send extracted text to Gemini as plain text input.

        For PDFs, text is extracted via PyMuPDF. For Word docs, text
        can be passed directly via text_override.

        Text is truncated to 50,000 characters to stay within context limits.
        Uses the LangChain model wrapper (text-only, no file upload).
        """
        if text_override:
            text = text_override
        else:
            text = extract_text_from_pdf(document_bytes)

        if not text.strip():
            logger.warning("No text available for extraction")
            return ExtractionResult(tables=[])

        prompt = (
            ROAMING_AGREEMENT_PROMPT
            if use_telecom_prompt
            else GENERIC_TABLE_EXTRACTION_PROMPT
        )

        full_prompt = f"{prompt}\n\n━━━ DOCUMENT TEXT ━━━\n{text[:50000]}"

        try:
            response = self.model.invoke(full_prompt)

            response_text = (
                response.content
                if hasattr(response, "content")
                else str(response)
            )

            return self._extract_json_from_response(response_text)

        except Exception as e:
            logger.error(f"Text-based Gemini call failed: {e}")
            return ExtractionResult(tables=[])

    # ═══════════════════════════════════════════════════════════════════
    # JSON response parser
    # ═══════════════════════════════════════════════════════════════════

    def _extract_json_from_response(
        self, raw_text: str
    ) -> Optional[ExtractionResult]:
        """
        Parse Gemini's raw text output into an ExtractionResult.

        Handles common response formatting issues:
        - JSON wrapped in markdown code fences
        - Extra text before/after the JSON body
        - Numeric values returned as numbers instead of strings
        """
        if not raw_text:
            return None

        # Strip markdown code fences
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Locate JSON object boundaries
        start_idx = text.find("{")
        end_idx = text.rfind("}")

        if start_idx == -1 or end_idx == -1:
            logger.error("No JSON object found in response")
            logger.debug(f"Response preview: {raw_text[:500]}")
            return None

        json_str = text[start_idx : end_idx + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Parse input preview: {json_str[:500]}")
            return None

        # Build ExtractionResult from parsed JSON
        tables = []
        raw_tables = data.get("tables", [])

        # Handle case where Gemini returns a list instead of {"tables": [...]}
        if not raw_tables and isinstance(data, list):
            raw_tables = data

        for t in raw_tables:
            if not isinstance(t, dict):
                continue

            title = t.get("title", "Untitled Table")
            headers = t.get("headers", [])
            rows = t.get("rows", [])

            # Coerce all values to strings (schema requirement)
            headers = [str(h) for h in headers]
            rows = [
                [str(cell) for cell in row]
                for row in rows
                if isinstance(row, list)
            ]

            if headers:
                tables.append(
                    TableData(title=title, headers=headers, rows=rows)
                )

        logger.info(f"Parsed {len(tables)} tables from response")
        return ExtractionResult(
            tables=tables,
            raw_text_summary=data.get("raw_text_summary", None),
        )
