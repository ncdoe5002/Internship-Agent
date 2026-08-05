import os
import json
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
from google import genai
from yaspin import yaspin

from .extractor_template import (
    IOTAgreement,
    AgmtHeaderStg,
    AgmtModelsStg,
    AgmtMdlNormalStg,
    AgmtCommitment,
)

def read_pdf_text(filePath, use_ocr=False):
    accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CUDA
    )
    
    # Pass the accelerator options into the pipeline
    pipeline_options = PdfPipelineOptions(
        accelerator_options=accelerator_options
    )
    pipeline_options.do_ocr = use_ocr
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    result = converter.convert(filePath)
    text = result.document.export_to_markdown()
    return text


def fill_fields(structuredText, API_KEY):
    client = genai.Client(api_key=API_KEY)

    template_path = os.path.join(os.path.dirname(__file__), "extractor_template.py")

    schema_file = client.files.upload(
        file=template_path
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
    
    return json.loads(response.text or "{}")


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