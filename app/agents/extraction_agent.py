"""
Extraction Agent — sends documents to Gemini for structured data extraction.

Implements a 3-tier fallback strategy for PDF extraction:
    1. Direct PDF upload to Gemini (native PDF support)
    2. PDF-to-image conversion + Gemini vision (handles scanned documents)
    3. Text extraction via PyMuPDF + Gemini text input (last resort)

Returns ExtractionResult containing parsed table data matching
the agreement staging table schemas.

Dependencies:
    google-generativeai (Gemini SDK)
    PyMuPDF >= 1.24.5

Path: app/agents/extraction_agent.py
      (Replaces existing file — _extract_from_pdf() and _extract_from_word()
      were declared in run() but never implemented, causing AttributeError
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
from app.services.extraction.excel_adapter import extract_from_excel

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
            document_bytes=pdf_bytes,
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
            # Requires docx_adapter.py implementation + python-docx
            logger.error("Word extraction not yet implemented")
            return ExtractionResult(tables=[])

        elif doc_type in ("xlsx", "xls", "csv"):
            # Handled by excel_adapter.py; should not route through here
            logger.error("Excel files should use excel_adapter.py directly")
            try:
                return extract_from_excel(payload.document_bytes)
            except Exception as e:
                logger.error(f"Excel Extraction failed:{e}")
                return ExtractionResult(tables=[])

        else:
            logger.error(f"Unsupported document type: {doc_type}")
            return ExtractionResult(tables=[])

    # ── PDF extraction with 3-tier fallback ─────────────────────────────

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
            result = self._extract_via_text(payload)
            if result and result.tables:
                logger.info(f"Text extraction succeeded: {len(result.tables)} tables")
                return result
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")

        logger.error("All PDF extraction attempts failed")
        return ExtractionResult(tables=[])

    # ── Attempt 1: Send PDF directly to Gemini ──────────────────────────

    def _send_pdf_to_gemini(
        self, pdf_bytes: bytes, prompt: str
    ) -> Optional[ExtractionResult]:
        """
        Send raw PDF to Gemini as multimodal input.

        Gemini 1.5 Flash/Pro accepts PDF files natively. The PDF is
        base64-encoded and sent as inline_data with application/pdf mime type.

        Uses the raw google-generativeai SDK instead of the LangChain wrapper
        because LangChain's ChatGoogleGenerativeAI does not reliably handle
        binary file uploads.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            logger.error("google-generativeai package not installed")
            return None

        # Encode PDF as base64 for the API (binary → text encoding)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # Multimodal request: PDF file + extraction prompt
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
            # Resolve model name from the LangChain wrapper
            model_name = getattr(self.model, "model", "gemini-1.5-flash")
            if model_name.startswith("models/"):
                model_name = model_name.replace("models/", "")

            genai_model = genai.GenerativeModel(model_name=model_name)

            response = genai_model.generate_content(
                content_parts,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,        # Low temperature for consistent extraction
                    max_output_tokens=8192,  # Large output buffer for multi-table JSON
                ),
            )

            return self._extract_json_from_response(response.text)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    # ── Attempt 2: Convert PDF pages to images, send to Gemini ──────────

    def _send_pdf_as_images(
        self, pdf_bytes: bytes, prompt: str
    ) -> Optional[ExtractionResult]:
        """
        Convert PDF pages to PNG images and send to Gemini vision.

        Handles scanned PDFs that have no text layer. Each page is
        rendered at 200 DPI and sent as an inline image.

        Capped at 20 pages to stay within Gemini's input token limit.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            return None

        # Render pages as PNG images (via pdf_adapter.py)
        page_images = pdf_to_images(pdf_bytes, dpi=200, max_pages=20)

        if not page_images:
            logger.warning("No images rendered from PDF")
            return None

        # Build multimodal content: page images + prompt
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

    # ── Attempt 3: Extract text, send as plain text to Gemini ───────────

    def _extract_via_text(
        self, payload: ExtractionPayload
    ) -> ExtractionResult:
        """
        Extract raw text from PDF via PyMuPDF, then send the text to Gemini.

        Least accurate method — table formatting is lost in text extraction.
        Text is truncated to 50,000 characters to stay within context limits.

        Uses the LangChain model wrapper (text-only input, no file upload).
        """
        text = extract_text_from_pdf(payload.document_bytes)

        if not text.strip():
            logger.warning("No text extracted — PDF may be scanned or empty")
            return ExtractionResult(tables=[])

        prompt = (
            ROAMING_AGREEMENT_PROMPT
            if payload.use_telecom_prompt
            else GENERIC_TABLE_EXTRACTION_PROMPT
        )

        # Combine prompt with extracted text, truncated to context limit
        full_prompt = f"{prompt}\n\n━━━ DOCUMENT TEXT ━━━\n{text[:50000]}"

        try:
            response = self.model.invoke(full_prompt)

            # LangChain returns AIMessage; extract text content
            response_text = (
                response.content
                if hasattr(response, "content")
                else str(response)
            )

            return self._extract_json_from_response(response_text)

        except Exception as e:
            logger.error(f"Text-based Gemini call failed: {e}")
            return ExtractionResult(tables=[])

    # ── JSON response parser ────────────────────────────────────────────

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