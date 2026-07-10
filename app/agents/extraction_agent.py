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
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from app.schemas.extraction import ExtractionResult


class ExtractionAgentInput(BaseModel):
    """
    Input schema for the Extraction Agent.

    Attributes:
        document_types: The raw bytes of the PDF document to be processed.
        filename: Optional filename of the document for identification purposes.
    """

    document_types: bytes = Field(description="Raw bytes of the PDF document")
    filename: str | None = Field(default=None, description="Optional filename for document identification")


class ExtractionAgent:
    """
    Agent responsible for extracting tariff tables from PDF documents.

    This agent uses a vision-capable language model to analyze PDF documents
    and extract structured tariff data in JSON format.

    Attributes:
        model: The language model instance (e.g., ChatOpenAI) used for extraction.
    """

    def __init__(self, model: Any):
        """
        Initialize the Extraction Agent.

        Args:
            model: A language model instance capable of vision processing.
        """
        self.model = model

    def run(self, payload: ExtractionAgentInput) -> ExtractionResult:
        """
        Execute the extraction process on the provided document.

        This method constructs a prompt with the JSON schema, creates LangChain messages
        with the document content, invokes the model, and parses the response into
        a structured ExtractionResult.

        Args:
            payload: Input containing the document bytes and optional filename.

        Returns:
            ExtractionResult: Structured data containing extracted tariff tables
                and text summary from the document.

        Raises:
            json.JSONDecodeError: If the model response cannot be parsed as JSON.
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
        
        response = self.model.invoke(messages)
        
        # Parse response content
        content = response.content
        if isinstance(content, list):
            # Handle structured output from models that return lists
            content = content[0] if content else ""
        
        # Extract JSON from response
        # The model should return JSON matching the ExtractionResult schema
        if isinstance(content, str):
            data = json.loads(content)
        else:
            # Handle case where content might be a dict or other format
            data = json.loads(str(content))
            
        return ExtractionResult.model_validate(data)
