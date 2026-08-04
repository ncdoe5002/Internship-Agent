# extractor_docling.py
#
# This script uses "docling" to read a PDF (with OCR if needed),
# then does simple semantic analysis on the text to fill in the
# schema objects from extractor_template.py.
#
# get_contents(filePath) is the main function.
# It returns a filled-in IOTAgreement, which contains:
#   - header          -> AgmtHeaderStg
#   - models          -> list of AgmtModelsStg
#   - normal_models   -> list of AgmtMdlNormalStg
#   - commitments     -> list of AgmtCommitment
#
# Install requirement:
#   pip install docling

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

from google import genai
from yaspin import yaspin
import json

from extractor_template import (
    IOTAgreement,
    AgmtHeaderStg,
    AgmtModelsStg,
    AgmtMdlNormalStg,
    AgmtCommitment,
)


def read_pdf_text(filePath, use_ocr=True):
    # Turns the PDF into plain text using docling.
    # use_ocr=True also reads scanned/image pages.
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = use_ocr
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    result = converter.convert(filePath)
    text = result.document.export_to_markdown()
    return text
from google import genai

def fill_fields(structuredText, API_KEY):

    client = genai.Client(api_key=API_KEY)

    schema_file = client.files.upload(
        file="extractor_template.py"
    )

    prompt = f"""
You are a data extraction engine.

You have two inputs:

1. DOCUMENT TEXT:
{structuredText}

2. TARGET PYDANTIC MODELS:
{schema_file}

Your task:

- Extract only information explicitly present in the document.
- Fill the provided fields.
- If a field is missing, return null.
- Do not guess values.
- Do not create additional fields.
- Return ONLY valid JSON.
- The JSON keys must exactly match the Pydantic models.

Output format:

{{
  "header": {{
      "agmt_id": null,
      "sender": null,
      "rp": null
  }},
  "model": {{
      "model_seq": null,
      "agmt_id": null,
      "model_type": null,
      "model_name": null
  }},
  "normal_model": {{
      "agmt_id": null,
      "model_seq": null,
      "rate_currency": null
  }},
  "commitment": {{
      "agmt_id": null,
      "commitment_name": null,
      "commitment_type": null,
      "amount": null
  }}
}}
"""
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=[
            prompt,
            schema_file
        ],
        config={
            "response_mime_type": "application/json"
        }
    )
    return json.loads(response.text)
    
from yaspin import yaspin

def get_contents(filePath, use_ocr, api_key):

    with yaspin(text="Extracting document with Docling...", color="cyan") as spinner:
        docling_dump = read_pdf_text(filePath=filePath, use_ocr=use_ocr)
        spinner.ok("✔")
        spinner.write("Docling extraction completed")

    with yaspin(text="Generating structured JSON...", color="cyan") as spinner:
        json_data = fill_fields(docling_dump, API_KEY=api_key)
        spinner.ok("✔")
        spinner.write("JSON generation completed")

    with yaspin(text="Validating agreement...", color="cyan") as spinner:
        agreement = IOTAgreement.model_validate(json_data)
        spinner.ok("✔")
        spinner.write("Agreement validation completed")

    return (
        agreement.header,
        agreement.model,
        agreement.normal_model,
        agreement.commitment,
    )
