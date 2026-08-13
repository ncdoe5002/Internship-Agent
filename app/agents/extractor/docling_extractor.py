# docling_extractor.py
import json, os
import time
from docling.datamodel.accelerator_options import (
    AcceleratorDevice,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from openai import OpenAI
from yaspin import yaspin
from google import genai
from google.genai import types
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

def clean_and_parse_json(raw_text: str) -> dict:
    """Helper to strip markdown fences and parse the JSON string."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rstrip("`").strip()
    return json.loads(cleaned)

def fill_fields(doc_text: str, API_KEY: str) -> dict:
    schema = json.dumps(IOTAgreement.model_json_schema(), indent=2)

    prompt = f"""
        You are a telecom roaming agreement analyst. Extract ALL structured data from this
        document into a specific JSON format based on the provided Pydantic schema. The document
        is a bilateral roaming agreement between two telecom operators.

        Return ONLY valid JSON. No markdown, no explanation, no code fences.
        The JSON MUST strictly conform to this schema:
        {schema}

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        GLOBAL EXTRACTION RULES
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        1. STRICT SCHEMA: Do not invent missing values; set absent non-required fields to null.
        2. CONFLICT RESOLUTION: When the same data point appears differently in prose/narrative text
        versus a structured table or numbered clause, ALWAYS prefer the table or clause value.
        Log the conflict in the 'remarks' field.
        3. DATA NORMALIZATION:
        - Dates MUST be normalized to YYYY-MM-DD format.
        - Currency codes MUST be uppercase ISO codes (e.g., 'EUR', 'USD', 'SDR'). If missing
            explicitly, infer from symbols (€ -> EUR, $ -> USD).
        - Boolean fields should be true or false.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        SECTION 1: "header" (Agreement Metadata)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Extract metadata governing the agreement (parties involved, dates, currency, rules).
        - sender: Operator proposing the agreement (TADIG code or operator name).
        - rp: Roaming partner (the other operator).
        - start_date / end_date: You MUST extract these if mentioned or implied by period clauses.
        - agmt_id: If the document contains an explicit agreement ID, reference number, or contract
        number, use that value. If NO explicit ID exists, you MUST auto-generate one using the
        format: "{{sender}}-{{rp}}-{{start_date}}" (e.g., "Orange-Etisalat-2025-01-01").
        - remarks: General notes, governing clauses, or conflict resolution logs.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        SECTION 2: "model" (Rate Models)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Pricing model definitions.
        - model_seq: Sequence number starting from 1.
        - model_type: "VOICE", "DATA", "SMS", "VoLTE", "CAMEL", etc.
        - model_name: Descriptive name of the pricing model.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        SECTION 3: "normal_model" (Service Charging Tiers)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Array of service charging tiers (MOC/SMS/Data rate per min/SMS/MB).
        - rec_type: "MOC" (mobile originated), "SMS", "DATA", "MTC", etc.
        - charge_field: This is the ACTUAL NUMERICAL RATE charged per unit (e.g., 0.15, 0.035, 0.022). 
        Extract the numerical value directly into this field. Do not include currency symbols.
        - rate_currency: Currency for these specific rates.
        - pra_rate_type: Distinguish between different rate structures:
        - "IOT" = base inter-operator tariff (standard/default rate).
        - "Incremental" / "IOT_OVERAGE" = rate applied above a volume threshold.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        SECTION 4: "commitment" (Financial & Volume Commitments)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Array of fixed revenues, send-or-pay amounts, and volume allowances.
        - commitment_name: Descriptive label from the document text.
        - commitment_type: "Send or Pay", "Fixed", "Variable", "Revenue Share", etc.
        - amount: Financial monetary target value (e.g., 550000.0). Extract monetary values here.
        - direction: "Inbound", "Outbound", or "Bilateral".
        - party_from / party_to: Committing operator and receiving operator.
        - Split compound commitments (e.g., a Send-or-Pay AND a traffic allowance) into separate objects.

        Document Text:
        {doc_text}
        """

    # ---------------------------------------------------------
    # ATTEMPT 1: LM STUDIO (LOCAL LLM) WITH RETRIES
    # ---------------------------------------------------------
    print("\n[LM Studio] Attempting extraction via local model...")
    
    # Uses host.docker.internal to punch through the Docker container to your host machine
    lm_client = OpenAI(
        base_url=os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234/v1"),
        api_key="lm-studio" # API Key is ignored by LM Studio but required by the OpenAI client
    )

    # Define the temperatures to cycle through on each attempt
    temperatures = [0.1, 0.4, 0.7]
    lm_success = False

    for attempt, temp in enumerate(temperatures, start=1):
        try:
            print(f"  -> Attempt {attempt}/3 (Temperature: {temp})...")
            lm_t0 = time.time()
            
            response = lm_client.chat.completions.create(
                model="local-model", # LM Studio automatically uses whatever is loaded
                messages=[
                    {"role": "system", "content": "You are a precise data extraction assistant. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=temp,
                max_tokens=16384,    # Increased token limit for large outputs
                timeout=600.0        # Increased timeout to 10 minutes (600 seconds)
            )
            
            raw_response = response.choices[0].message.content
            if not raw_response:
                raise ValueError("Empty response from LM Studio")
                
            parsed_data = clean_and_parse_json(raw_response)
            print(f"[LM Studio] Success! Extraction completed in {time.time() - lm_t0:.2f}s")
            
            lm_success = True
            return parsed_data # Exit the function entirely on success

        except Exception as e:
            print(f"  -> Attempt {attempt} failed: {str(e)}")
            # The loop will automatically continue to the next temperature

    # If the loop finishes and lm_success is still False, it falls through to Gemini
    if not lm_success:
        print("[Gemini] All LM Studio attempts failed. Initiating fallback extraction...")

    # ---------------------------------------------------------
    # ATTEMPT 2: GEMINI (FALLBACK)
    # ---------------------------------------------------------
    try:
        gem_t0 = time.time()
        gemini_client = genai.Client(api_key=API_KEY)
        
        response = gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        
        raw_response = response.text
        if not raw_response:
            raise ValueError(f"Empty response from Gemini. Full response: {response}")

        parsed_data = clean_and_parse_json(raw_response)
        print(f"[Gemini] Success! Fallback extraction completed in {time.time() - gem_t0:.2f}s")
        return parsed_data

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from Fallback LLM: {raw_response}")
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
        text="Generating structured JSON via LLM...",
        color="cyan",
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
