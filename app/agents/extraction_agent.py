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

import pandas as pd
from docx import Document
from openpyxl import load_workbook
from pydantic import BaseModel, Field, ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from app.schemas.extraction import ExtractionResult
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
    filename: str | None = Field(default=None, description="Optional filename for document identification")
    file_type: str = Field(default="pdf", description="File type: pdf, xlsx, xls, docx, doc")


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

    def _extract_from_excel(self, file_bytes: bytes) -> ExtractionResult:
        """
        Extract tables from Excel file using pandas/openpyxl.

        Args:
            file_bytes: Raw bytes of the Excel file

        Returns:
            ExtractionResult with tables extracted from Excel
        """
        logger.info("Extracting tables from Excel file")
        tables = []
        
        try:
            # Use pandas to read all sheets
            excel_file = BytesIO(file_bytes)
            
            # Try reading with openpyxl for .xlsx
            try:
                xls = pd.ExcelFile(excel_file, engine='openpyxl')
            except:
                # Fallback to xlrd for .xls
                xls = pd.ExcelFile(excel_file, engine='xlrd')
            
            sheet_count = 0
            total_rows = 0
            
            for sheet_name in xls.sheet_names:
                if sheet_count >= MAX_TABLE_COUNT:
                    logger.warning(f"Reached max table count ({MAX_TABLE_COUNT}), stopping Excel extraction")
                    break
                
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                
                # Skip empty sheets
                if df.empty:
                    continue
                
                # Convert DataFrame to table format
                rows = []
                for _, row in df.iterrows():
                    if total_rows >= MAX_ROW_COUNT:
                        logger.warning(f"Reached max row count ({MAX_ROW_COUNT}), stopping Excel extraction")
                        break
                    
                    # Convert all values to strings, handling NaN
                    row_str = [str(v) if pd.notna(v) else "" for v in row]
                    rows.append(row_str)
                    total_rows += 1
                
                if rows:
                    # First row as headers
                    headers = rows[0] if rows else []
                    data_rows = rows[1:] if len(rows) > 1 else []
                    
                    tables.append({
                        "title": sheet_name or f"Sheet {sheet_count + 1}",
                        "headers": headers,
                        "rows": data_rows
                    })
                    sheet_count += 1
            
            logger.info(f"Extracted {len(tables)} tables from Excel")
            
        except Exception as e:
            logger.error(f"Excel extraction failed: {str(e)}")
            raise ValueError(f"Failed to extract from Excel file: {str(e)}")
        
        return ExtractionResult(
            tables=tables,
            raw_text_summary=f"Extracted {len(tables)} tables from Excel file"
        )

    def _extract_from_word(self, file_bytes: bytes) -> ExtractionResult:
        """
        Extract tables from Word document using python-docx.

        Args:
            file_bytes: Raw bytes of the Word document

        Returns:
            ExtractionResult with tables extracted from Word
        """
        logger.info("Extracting tables from Word document")
        tables = []
        
        try:
            doc = Document(BytesIO(file_bytes))
            
            table_count = 0
            total_rows = 0
            
            for table in doc.tables:
                if table_count >= MAX_TABLE_COUNT:
                    logger.warning(f"Reached max table count ({MAX_TABLE_COUNT}), stopping Word extraction")
                    break
                
                rows = []
                for row in table.rows:
                    if total_rows >= MAX_ROW_COUNT:
                        logger.warning(f"Reached max row count ({MAX_ROW_COUNT}), stopping Word extraction")
                        break
                    
                    # Extract cell text
                    row_data = [cell.text.strip() for cell in row.cells]
                    rows.append(row_data)
                    total_rows += 1
                
                if rows:
                    # First row as headers
                    headers = rows[0] if rows else []
                    data_rows = rows[1:] if len(rows) > 1 else []
                    
                    tables.append({
                        "title": f"Table {table_count + 1}",
                        "headers": headers,
                        "rows": data_rows
                    })
                    table_count += 1
            
            logger.info(f"Extracted {len(tables)} tables from Word document")
            
        except Exception as e:
            logger.error(f"Word extraction failed: {str(e)}")
            raise ValueError(f"Failed to extract from Word document: {str(e)}")
        
        return ExtractionResult(
            tables=tables,
            raw_text_summary=f"Extracted {len(tables)} tables from Word document"
        )

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
            return self._extract_from_excel(payload.document_types)
        elif file_type in ["docx", "doc"]:
            return self._extract_from_word(payload.document_types)
        elif file_type == "pdf":
            return self._extract_from_pdf(payload)
        else:
            raise ValueError(f"Unsupported file type: {file_type}. Supported: pdf, xlsx, xls, docx, doc")

    def _extract_from_pdf(self, payload: ExtractionAgentInput) -> ExtractionResult:
        """
        Extract tables from PDF using vision model with retry logic.

        Args:
            payload: Input containing the PDF document bytes and filename.

        Returns:
            ExtractionResult: Structured data containing extracted tariff tables
                and text summary from the document.

        Raises:
            json.JSONDecodeError: If the model response cannot be parsed as JSON after retry.
            ValidationError: If the parsed data doesn't match the ExtractionResult schema.
        """
        prompt = (
            "Extract the tariff tables from the document provided and return the extracted data in JSON matching this schema"
            f"{ExtractionResult.model_json_schema()}"
        )
        
        # Create messages for LangChain model
        # System message defines the extraction task and expected output format
        # Human message contains the document to be processed
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": f"Filename: {payload.filename or 'unknown'}"},
                    {
                        "type": "media",
                        "media_type": "application/pdf",
                        "data": payload.document_types
                    }
                ]
            )
        ]
        
        # First attempt
        response = self.model.invoke(messages)
        
        # Parse response content
        content = response.content
        if isinstance(content, list):
            # Handle structured output from models that return lists
            content = content[0] if content else ""
        
        # Extract JSON from response, handling code fences
        json_str = self._extract_json_from_response(content) if isinstance(content, str) else str(content)
        
        try:
            data = json.loads(json_str)
            return ExtractionResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"First attempt failed: {str(e)}. Retrying with corrective reprompt.")
            
            # Retry with corrective reprompt
            corrective_prompt = (
                "Your previous response could not be parsed as valid JSON. "
                "Please extract the tariff tables from the document and return ONLY valid JSON "
                f"matching this schema: {ExtractionResult.model_json_schema()}. "
                "Do not include markdown code fences, explanations, or any text outside the JSON."
            )
            
            retry_messages = [
                SystemMessage(content=corrective_prompt),
                HumanMessage(
                    content=[
                        {"type": "text", "text": f"Filename: {payload.filename or 'unknown'}"},
                        {
                            "type": "media",
                            "media_type": "application/pdf",
                            "data": payload.document_types
                        }
                    ]
                )
            ]
            
            retry_response = self.model.invoke(retry_messages)
            retry_content = retry_response.content
            
            if isinstance(retry_content, list):
                retry_content = retry_content[0] if retry_content else ""
            
            retry_json_str = self._extract_json_from_response(retry_content) if isinstance(retry_content, str) else str(retry_content)
            
            try:
                data = json.loads(retry_json_str)
                return ExtractionResult.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Retry failed: {str(e)}")
                raise
