import json
import os

import google.generativeai as genai

from ..schemas.extraction import ExtractionResult

EXTRACTION_PROMPT = """
You are a data extraction assistant. Extract all tabular data from the provided PDF content.
Return a JSON object with this exact structure:
{
  "tables": [
    {
      "title": "Table name or empty string",
      "headers": ["Column 1", "Column 2", ...],
      "rows": [
        ["cell value", "cell value", ...],
        ...
      ]
    }
  ],
  "raw_text_summary": "brief summary of the document"
}
Return only valid JSON, no markdown code fences.
"""


def extract_table_data(pdf_bytes: bytes) -> ExtractionResult:
    """Send PDF bytes to Gemini and return validated ExtractionResult."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    response = model.generate_content(
        [
            EXTRACTION_PROMPT,
            {"mime_type": "application/pdf", "data": pdf_bytes},
        ]
    )

    raw_json = response.text.strip()
    data = json.loads(raw_json)
    return ExtractionResult(**data)
