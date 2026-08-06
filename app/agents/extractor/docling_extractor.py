import json
import os
import time
from docling.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from openai import OpenAI
from yaspin import yaspin

from .extractor_template import IOTAgreement

# =====================================================================
# TOGGLE THIS FOR FAST TESTING:
# Set to True  => Skips Docling execution and uses instant sample text.
# Set to False => Runs real GPU-accelerated Docling extraction.
# =====================================================================
MOCK_DOCLING = False

# Global Converter Caching (used when MOCK_DOCLING = False)
_global_converter = None


def get_converter(use_ocr: bool):
    global _global_converter
    if _global_converter is None:
        accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CUDA)
        pipeline_options = PdfPipelineOptions(accelerator_options=accelerator_options)
        pipeline_options.do_ocr = use_ocr
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options = TableStructureOptions(
            do_cell_matching=True
        )

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


def read_pdf_text(filePath: str, use_ocr: bool = False) -> str:
    """Reads PDF layout using Docling with execution time tracking."""
    if MOCK_DOCLING:
        return SAMPLE_DOCLING_MARKDOWN

    t0 = time.time()
    converter = get_converter(use_ocr=use_ocr)
    result = converter.convert(filePath)
    extracted_md = result.document.export_to_markdown()

    page_count = (
        len(result.document.pages) if hasattr(result.document, "pages") else "N/A"
    )
    print(
        f"[Docling] Extracted {len(extracted_md)} chars across {page_count} page(s) in {time.time() - t0:.2f}s"
    )

    return extracted_md


def fill_fields(doc_text: str, API_KEY: str) -> dict:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )

    schema = json.dumps(IOTAgreement.model_json_schema(), indent=2)

    prompt = f"""
            You are extracting structured data from a telecom roaming agreement into a Pydantic schema.

            Return ONLY valid JSON.

            The JSON MUST strictly conform to this schema:
            {schema}

            CRITICAL EXTRACTION RULES:
            1. 'header': Extract metadata (parties, start_date, end_date, currency_code).
               - You MUST extract both start_date and end_date if mentioned or implied by period clauses.
               - Extract currency_code (e.g., 'EUR', 'USD'). If missing explicitly, infer from symbols (€ -> EUR, $ -> USD).
               - If 'agmt_id' is missing from document text, auto-generate as format: "{{sender}}-{{rp}}-{{start_date}}".
            2. 'normal_model': Array of service charging tiers (MOC/SMS/Data rate per min/SMS/MB).
               - Extract rate values into 'rate_val' and charge units into 'charge_field'.
            3. 'commitment': Array of fixed revenues, send-or-pay amounts, and volume allowances.
               - Separate monetary values into 'amount' and traffic caps into 'volume_value' / 'volume_unit'.
            4. Do not invent missing values; set absent non-required fields to null.

            Document Text:
            {doc_text}
            """

    t0 = time.time()
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b:free",
        messages=[
            {
                "role": "system",
                "content": "You are a precise data extraction assistant. Always output valid raw JSON without markdown formatting.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=8000,
    )
    print(f"[OpenRouter] LLM payload generation completed in {time.time() - t0:.2f}s")

    raw_response = response.choices[0].message.content
    if not raw_response:
        raise ValueError(f"Empty response from OpenRouter. Full response: {response}")

    try:
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response.lstrip("`")
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:]
            cleaned_response = cleaned_response.rstrip("`").strip()

        return json.loads(cleaned_response)

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from LLM: {raw_response}")
        raise e


def get_contents(filePath: str, use_ocr: bool, api_key: str):
    status_msg = (
        "Using Mock Docling output..."
        if MOCK_DOCLING
        else "Extracting document with Docling..."
    )

    with yaspin(text=status_msg, color="cyan") as spinner:
        docling_dump = read_pdf_text(filePath=filePath, use_ocr=use_ocr)
        spinner.ok("✔")
        spinner.write("Text extraction completed")

    with yaspin(
        text="Generating structured JSON via OpenRouter...", color="cyan"
    ) as spinner:
        json_data = fill_fields(docling_dump, API_KEY=api_key)
        spinner.ok("✔")
        spinner.write("JSON generation completed")

    with yaspin(text="Validating agreement schema...", color="cyan") as spinner:
        if isinstance(json_data, list):
            json_data = json_data[0] if json_data else {}

        agreement = IOTAgreement.model_validate(json_data)

        models_count = (
            len(agreement.model)
            if isinstance(agreement.model, list)
            else (1 if agreement.model else 0)
        )
        normal_count = (
            len(agreement.normal_model)
            if isinstance(agreement.normal_model, list)
            else (1 if agreement.normal_model else 0)
        )
        commitment_count = (
            len(agreement.commitment)
            if isinstance(agreement.commitment, list)
            else (1 if agreement.commitment else 0)
        )

        print("HEADER:", agreement.header)
        print("MODELS:", models_count)
        print("NORMAL MODELS:", normal_count)
        print("COMMITMENTS:", commitment_count)

        if not any(
            [
                agreement.header,
                agreement.model,
                agreement.normal_model,
                agreement.commitment,
            ]
        ):
            raise ValueError("LLM extraction returned empty agreement structure")

        spinner.ok("✔")
        spinner.write("Agreement validation completed")

    return (
        agreement.header,
        agreement.model,
        agreement.normal_model,
        agreement.commitment,
    )
