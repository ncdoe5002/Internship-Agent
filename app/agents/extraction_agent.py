"""
Extraction Agent - Extracts tariff tables from PDF documents.

This agent uses a language model to extract structured tariff data from PDF documents.
It processes the document content and returns the extracted data in a structured JSON format
matching the ExtractionResult schema.

Usage:
    model = ChatOpenAI(model="gpt-4-vision-preview")
    agent = ExtractionAgent(model)
    result = agent.run(payload)
"""

from __future__ import annotations

import json
import logging
import re
from io import BytesIO
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from app.schemas.extraction import ExtractionResult
from app.services.extraction.excel_adapter import extract_from_excel
from app.services.storage import MAX_TABLE_COUNT, MAX_ROW_COUNT

logger = logging.getLogger(__name__)


class ExtractionAgentInput(BaseModel):
    """
    Input schema for the Extraction Agent.

    Attributes:
        document_types: The raw bytes of the document to be processed.
        filename: Optional filename of the document for identification purposes.
        file_type: Type of file (pdf, xlsx, xls, docx, doc)
    """

    document_types: bytes = Field(description="Raw bytes of the document")
    filename: str | None = Field(
        default=None, description="Optional filename for document identification"
    )
    file_type: str = Field(
        default="pdf", description="File type: pdf, xlsx, xls, docx, doc"
    )


class ExtractionAgent:
    """
    Agent responsible for extracting tariff tables from documents.

    This agent extracts structured tariff data from PDF, Excel, and Word documents.
    PDF files use a vision-capable language model, while Excel and Word files are
    parsed directly from their document structure.

    Attributes:
        model: The language model instance (e.g., ChatOpenAI) used for PDF extraction.
    """

    def __init__(self, model: Any):
        """
        Initialize the Extraction Agent.

        Args:
            model: A language model instance capable of vision processing.
        """
        self.model = model

    def _extract_json_from_response(self, content: str) -> str:
        """
        Extract JSON from model response, handling markdown code fences.

        Args:
            content: Raw response content from the model

        Returns:
            Extracted JSON string without code fences
        """
        # Check for markdown code fences
        if "```json" in content or "```" in content:
            # Extract content between code fences
            pattern = r"```(?:json)?\s*([\s\S]*?)```"
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip()

        # If no code fences, return content as-is
        return content.strip()

    def run(self, payload: ExtractionAgentInput) -> ExtractionResult:
        """
        Execute the extraction process on the provided document.

        This method branches by file type:
        - PDF: Uses vision-capable language model with retry logic
        - Excel (.xlsx, .xls): Parses directly using pandas/openpyxl
        - Word (.docx, .doc): Parses tables directly using python-docx

        All paths converge on the same ExtractionResult schema.

        Args:
            payload: Input containing the document bytes, filename, and file type.

        Returns:
            ExtractionResult: Structured data containing extracted tariff tables
                and text summary from the document.

        Raises:
            ValueError: If file type is unsupported or extraction fails.
            json.JSONDecodeError: If the model response cannot be parsed as JSON after retry (PDF only).
            ValidationError: If the parsed data doesn't match the ExtractionResult schema.
        """
        file_type = payload.file_type.lower()

        # Branch by file type
        if file_type in ["xlsx", "xls"]:
            return extract_from_excel(payload.document_types)
        elif file_type in ["docx", "doc"]:
            return self._extract_from_word(payload.document_types)
        elif file_type == "pdf":
            return self._extract_from_pdf(payload)
        else:
            raise ValueError(
                f"Unsupported file type: {file_type}. Supported: pdf, xlsx, xls, docx, doc"
            )
