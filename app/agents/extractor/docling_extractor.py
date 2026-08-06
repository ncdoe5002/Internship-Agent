import os
import json
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
import json
from openai import OpenAI
from google import genai
from google.genai import types
from yaspin import yaspin

from .extractor_template import IOTAgreement

# =====================================================================
# TOGGLE THIS FOR FAST TESTING:
# Set to True  => Skips Docling execution and uses instant sample text.
# Set to False => Runs real GPU-accelerated Docling extraction.
# =====================================================================
MOCK_DOCLING = True

# Global Converter Caching (used when MOCK_DOCLING = False)
_global_converter = None

def get_converter(use_ocr):
    global _global_converter
    if _global_converter is None:
        accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CUDA)
        pipeline_options = PdfPipelineOptions(accelerator_options=accelerator_options)
        pipeline_options.do_ocr = use_ocr
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)

        _global_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    return _global_converter


# Sample text extracted from Orange_IOT_Egypt 2024_sample_tobe_shared.pdf
SAMPLE_DOCLING_MARKDOWN = """
# Back-to-Back IOT Discount Letter Number 5
Effective Date: 1 January 2024

Parties:
(1) Etisalat Misr S.A.E. (registered in Egypt, Cairo)
(2) Emirates Telecommunications Group Company PJSC ("Etisalat") (Abu Dhabi, UAE)

Framework Agreement context:
Orange Affiliates (represented by Orange S.A., 78 rue Olivier de Serres, 75015 Paris, France) and Etisalat.

1. DEFINITIONS & PERIOD
- Discount Period 1: 1 January 2024 until 31 December 2024.
- Currency: EUR (€)

2. COMMITMENTS AND IOT DISCOUNT RATES

2.1. Etisalat Misr Send or Pay Commitment:
- Total Commitment: €550,000
- Included Volumes:
  * MOC: 800,000 min
  * SMS: 455,000 units
  * Data: 58,000,000 MB
- Minimum Guaranteed Revenue (Fixed): €90,000

Incremental rates (over allowance):
- MOC: €0.15 / min
- SMS: €0.035 / SMS
- Data: €0.022 / MB

2.2. Orange EU Affiliates Send or Pay Commitment:
- Total Commitment: €5,390,000
- Included Allowance Volumes:
  * MOC: 330,000 min
  * SMS: 140,000 units
  * Data: 88,500,000 MB
- Fixed Revenue: €375,000
- Variable Revenue share pool: €75,000

Incremental rates (over allowance):
- MOC: €0.15 / min
- SMS: €0.025 / SMS
- Data: €0.033 / MB

3. AFFILIATES LIST (TADIG CODES)
- Orange EU: FRAF1, BELMO, LUXVM, ESPRT, ESPJZ, POL03, ROMMR, SVKGT, MDAVX, GLP01
- Etisalat Affiliates: EGYEM (Etisalat Misr), AFGEA, PAKUF
"""



def read_pdf_text(filePath, use_ocr=False):
    """
    Reads PDF layout. If MOCK_DOCLING is enabled, returns instant sample text.
    """
    if MOCK_DOCLING:
        return SAMPLE_DOCLING_MARKDOWN

    # Real Docling execution path
    converter = get_converter(use_ocr=use_ocr)
    result = converter.convert(filePath)
    return result.document.export_to_markdown()


def fill_fields(doc_text: str, API_KEY: str) -> dict:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )
    
    prompt = f"""
    Extract the telecom agreement details from the following document.
    You must respond ONLY with a valid JSON object matching the required schema.
    
    Document Text:
    {doc_text}
    """
    
    response = client.chat.completions.create(
        model="google/gemini-3.5-flash", 
        messages=[
            {"role": "system", "content": "You are a precise data extraction assistant. Always output valid JSON without markdown wrapping."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        max_tokens=2000
    )
    
    raw_response = response.choices[0].message.content

    # 1. Type Guard: Satisfies Pyright/Pylance by ensuring raw_response is a string
    if not raw_response:
        raise ValueError("Received an empty or null response from OpenRouter.")

    try:
        # 2. Clean up markdown code blocks if present
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            # Remove leading ```json or ``` and trailing ```
            cleaned_response = cleaned_response.lstrip("`")
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:]
            cleaned_response = cleaned_response.rstrip("`").strip()

        # 3. Safe to pass to json.loads now
        json_data = json.loads(cleaned_response)
        return json_data

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from LLM: {raw_response}")
        raise e


def get_contents(filePath, use_ocr, api_key):
    status_msg = "Using Mock Docling output..." if MOCK_DOCLING else "Extracting document with Docling..."
    
    with yaspin(text=status_msg, color="cyan") as spinner:
        docling_dump = read_pdf_text(filePath=filePath, use_ocr=use_ocr)
        spinner.ok("✔")
        spinner.write("Text extraction completed")

    # Updated logging text here
    with yaspin(text="Generating structured JSON via OpenRouter...", color="cyan") as spinner:
        # Pass the OpenRouter API key into fill_fields
        json_data = fill_fields(docling_dump, API_KEY=api_key)
        spinner.ok("✔")
        spinner.write("JSON generation completed")

    with yaspin(text="Validating agreement schema...", color="cyan") as spinner:
        agreement = IOTAgreement.model_validate(json_data)
        spinner.ok("✔")
        spinner.write("Agreement validation completed")

    return (
        agreement.header,
        agreement.model,
        agreement.normal_model,
        agreement.commitment,
    )
