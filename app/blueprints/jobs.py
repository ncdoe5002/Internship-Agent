import os
import logging
from typing import Any, cast
from flask import current_app
from celery import shared_task
from app.extensions import db
import json
from app.models.document import Document
from app.agents.extractor.docling_extractor import get_contents
from app.services.db_mapper import get_baseline_data
from app.agents.orchestrator import Orchestrator, OrchestratorInput

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_contract_task(self, document_id: int, contract_text: str):
    doc = Document.query.get(document_id)
    if not doc:
        logger.error(f"Document with ID {document_id} not found in database. Aborting task.")
        return
    
    try:
        doc.current_step = 2
        db.session.commit()

        file_path = os.path.join(current_app.root_path, "static", doc.file_key)
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        # =========================================================
        # 🚀 MOCK DATA TOGGLE
        # =========================================================
        USE_MOCK_DATA = True
        mock_file_path = os.path.join(current_app.root_path, "static", "mock_payload.json")
        payload = {}

        if USE_MOCK_DATA and os.path.exists(mock_file_path):
            logger.info("⚡ FAST MODE: Loading extracted data from mock_payload.json")
            with open(mock_file_path, "r") as f:
                payload = json.load(f)
        else:
            logger.info("🐌 REAL MODE: Running Docling and OpenRouter extraction...")
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            extracted = cast(Any, get_contents(
                filePath=file_path,
                use_ocr=False,
                api_key=api_key
            ))
            header, model, normal_model, commitment = extracted

            def to_dict(obj):
                if not obj:
                    return {}
                if hasattr(obj, "model_dump"):  # Pydantic v2
                    return obj.model_dump()
                elif hasattr(obj, "dict"):      # Pydantic v1
                    return obj.dict()
                return obj if isinstance(obj, dict) else {}

            payload = {
                "header": to_dict(header),
                "model": [m.model_dump() for m in model] if model else [],
                "normal_model": [nm.model_dump() for nm in normal_model] if normal_model else [],
                "commitment": [c.model_dump() for c in commitment] if commitment else [],
            }

            if USE_MOCK_DATA:
                logger.info("💾 SAVING output to mock_payload.json for next time!")
                with open(mock_file_path, "w") as f:
                    json.dump(payload, f, indent=4)
        # =========================================================

        # 1. Save JSON to the DB 
        doc.extracted_data = payload
        
        # 2. Safely truncate ID to prevent PostgreSQL 50-char crash
        raw_agmt_id = payload.get("header", {}).get("agmt_id", "")
        doc.agmt_id = raw_agmt_id[:50] if raw_agmt_id else None
        
        # 3. Get Baseline Data
        baseline_tables = get_baseline_data(doc.partner_name)
        doc.baseline_data = baseline_tables

        # 4. Run Verification & Risk Pipeline
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
        
        if pipeline_result.verification.status == "FAILED" or pipeline_result.risk.highest_risk == "HIGH":
            doc.status = 'REVIEW'
        else:
            doc.status = 'READY'
            
        # ==========================================
        # NEW: SAVE RICH DATA & CONFIDENCE SCORES
        # ==========================================
        
        # 1. Convert the nested Pydantic OrchestratorOutput into a pure Python dictionary
        result_dict = pipeline_result.model_dump()
        rich_fields = result_dict.get("field_details", {})
        
        # 2. Map the Orchestrator's plural keys back to the singular keys the UI expects
        rich_payload = {
            "header": rich_fields.get("header", {}),
            "model": rich_fields.get("models", []),
            "normal_model": rich_fields.get("rates", []),
            "commitment": rich_fields.get("commitments", [])
        }
        
        # 3. Overwrite the flat JSON with the rich JSON so the UI receives 'value', 'confidence_score', and 'flags'
        doc.extracted_data = rich_payload
        
        # 4. Save the global confidence score directly to the database column
        doc.confidence_score = pipeline_result.verification.confidence
        
        # ==========================================

        doc.current_step = 5
        if pipeline_result.errors:
            doc.error_message = " | ".join(pipeline_result.errors)
            
        db.session.commit()

    except Exception as e:
        logger.error(f"AI Processing failed for document {document_id}: {str(e)}")
        db.session.rollback()
        doc = Document.query.get(document_id)
        if doc:
            doc.status = "FAILED"
            doc.error_message = str(e)
            db.session.commit()
        raise e
