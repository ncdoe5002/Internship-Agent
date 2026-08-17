"""
Background Jobs Pipeline
------------------------
Contains asynchronous Celery tasks for heavy computational workloads.
Manages the end-to-end AI document processing lifecycle, including Docling PDF 
extraction, Gemini LLM structuring, Orchestrator data validation, baseline 
comparison, and local database state management.
"""

import os
import logging
from typing import Any, cast
from flask import current_app
from celery import shared_task

# Database & Domain Models
from app.extensions import db
from app.models.document import Document
from app.services.db_mapper import get_baseline_data

# AI & Extraction Agents
from app.agents.extractor.docling_extractor import get_contents
from app.agents.orchestrator import Orchestrator, OrchestratorInput

logger = logging.getLogger(__name__)

# =====================================================================
# ASYNCHRONOUS CELERY TASKS
# =====================================================================

@shared_task(bind=True)
def process_contract_task(self, document_id: int, contract_text: str):
    """
    Main background pipeline for processing uploaded roaming contracts.
    Executes a multi-step pipeline:
      1. Hardware-accelerated document extraction (Docling).
      2. LLM-based JSON mapping against Pydantic schemas.
      3. Orchestrator-driven verification and risk assessment.
      4. Persisting the rich result payload to the database.
      
    Args:
        document_id (int): Primary key of the Document record.
        contract_text (str): Raw extracted text from initial upload processing.
    """
    # Retrieve active document context
    doc = Document.query.get(document_id)
    if not doc:
        logger.error(f"Document with ID {document_id} not found in database. Aborting task.")
        return

    try:
        # Step 1: Update UI tracking state
        doc.current_step = 2
        db.session.commit()

        # Step 2: Extract structured tables & layout via Docling + LLM
        file_path = os.path.join(current_app.root_path, "static", doc.file_key)
        api_key = os.environ.get("GEMINI_API_KEY", "")
        extracted = cast(
            Any, get_contents(filePath=file_path, use_ocr=False, api_key=api_key)
        )
        header, model, normal_model, commitment = extracted

        # Internal helper to safely flatten Pydantic v1/v2 models into pure dicts
        def to_dict(obj):
            if obj is None:
                return {}
            if isinstance(obj, list):
                return [to_dict(item) if hasattr(item, 'model_dump') or hasattr(item, 'dict') else item for item in obj]
            if hasattr(obj, "model_dump"):  # Pydantic v2
                return obj.model_dump()
            elif hasattr(obj, "dict"):      # Pydantic v1
                return obj.dict()
            return obj if isinstance(obj, dict) else {}

        # Construct initial flat payload from LLM extraction
        payload = {
            "header": to_dict(header),
            "model": to_dict(model),
            "normal_model": to_dict(normal_model),
            "commitment": to_dict(commitment),
        }

        # Step 3: Map baseline data (existing prod records) for delta comparison
        doc.extracted_data = payload
        header_data = payload.get("header", {})
        doc.agmt_id = header_data.get("agmt_id") if isinstance(header_data, dict) else None

        baseline_tables = get_baseline_data(doc.partner_name)
        doc.baseline_data = baseline_tables

        # Step 4: Run Verification & Risk Orchestrator
        orchestrator = Orchestrator()
        pipeline_input = OrchestratorInput(
            file_path=file_path,
            filename=doc.filename,
            partner_name=doc.partner_name,
            raw_doc_text=contract_text,
            baseline_data=baseline_tables,
            use_telecom_prompt=True,
            pre_extracted_data=payload  
        )

        pipeline_result = orchestrator.run(pipeline_input)
        doc.current_step = 4
        
        # Assess orchestrator outcome to determine routing queue
        if (pipeline_result.verification.status == "FAILED" or pipeline_result.risk.highest_risk == "HIGH"):
            doc.status = "REVIEW" # Requires manual intervention
        else:
            doc.status = 'READY'  # Safe to proceed
            
        # ==========================================
        # Step 5: SAVE RICH DATA & CONFIDENCE SCORES
        # ==========================================
        
        # 1. Convert nested Pydantic OrchestratorOutput into a pure Python dictionary
        result_dict = pipeline_result.model_dump()
        rich_fields = result_dict.get("field_details", {})
        
        # 2. Map Orchestrator's plural keys back to the singular keys expected by UI templates
        rich_payload = {
            "header": rich_fields.get("header", {}),
            "model": rich_fields.get("models", []),
            "normal_model": rich_fields.get("rates", []),
            "commitment": rich_fields.get("commitments", [])
        }
        
        # 3. Overwrite temporary flat JSON with rich JSON (containing 'value', 'confidence', 'flags')
        doc.extracted_data = rich_payload
        
        # 4. Bind global confidence score to Document row
        doc.confidence_score = pipeline_result.verification.confidence
        
        # Finalize successful pipeline state
        doc.current_step = 5
        if pipeline_result.errors:
            doc.error_message = " | ".join(pipeline_result.errors)
        db.session.commit()

    except Exception as e:
        # Global Error Boundary: Safely catch faults, rollback broken state, and alert UI
        logger.error(f"AI Processing failed for document {document_id}: {str(e)}")
        db.session.rollback()  
        
        doc = Document.query.get(document_id)
        if doc:
            doc.status = "FAILED"
            doc.error_message = str(e)
            db.session.commit()
        raise e
