import os
import logging
from typing import Any, cast
from flask import current_app
from celery import shared_task
from app.extensions import db

from app.models.document import Document
from app.agents.extractor.docling_extractor import get_contents
from app.services.db_mapper import save_extracted_tables_to_db, get_baseline_data
from app.agents.orchestrator import Orchestrator, OrchestratorInput

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_contract_task(self, document_id: int, contract_text: str):
    doc = Document.query.get(document_id)
    
    # 1. Early exit check for Pyright type safety
    if not doc:
        logger.error(f"Document with ID {document_id} not found in database. Aborting task.")
        return
    
    try:
        # Update UI: Step 2
        doc.current_step = 2
        db.session.commit()

        # 2. Resolve PDF file path
        file_path = os.path.join(current_app.root_path, "static", doc.file_key)
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        # 3. Extract structured Pydantic objects using Docling + Gemini
        api_key = os.environ.get("GEMINI_API_KEY", "")
        extracted = cast(Any, get_contents(
            filePath=file_path,
            use_ocr=False,
            api_key=api_key
        ))
        header, model, normal_model, commitment = extracted

        # ----------------- DEBUG LOGS -----------------

        import json
        def to_dict(obj):
            if hasattr(obj, "model_dump"):  # Pydantic v2
                return obj.model_dump()
            elif hasattr(obj, "dict"):      # Pydantic v1
                return obj.dict()
            return str(obj)

        debug_data = {
            "header": to_dict(header),
            "model": to_dict(model),
            "normal_model": to_dict(normal_model),
            "commitment": to_dict(commitment),
        }

        with open("extracted_output_debug.json", "w") as f:
            json.dump(debug_data, f, indent=4, default=str)
        
        logger.info("Saved extracted output to extracted_output_debug.json")
        # ----------------------------------------------

        # 4. Save extracted objects directly into Staging tables
        save_extracted_tables_to_db(header, model, normal_model, commitment, document_id)

        # 5. Fetch production baseline data for comparison
        baseline_tables = get_baseline_data(doc.partner_name)

        # 6. Run Orchestrator Verification & Risk Pipeline
        orchestrator = Orchestrator()
        payload = OrchestratorInput(
            pdf_bytes=pdf_bytes,
            filename=doc.filename,
            partner_name=doc.partner_name,
            raw_doc_text=contract_text,
            baseline_data=baseline_tables,
            use_telecom_prompt=True
        )
        
        pipeline_result = orchestrator.run(payload)

        # Update UI: Step 4
        doc.current_step = 4
        db.session.commit()

        # 7. Finalize Document status based on Verification & Risk assessment
        if pipeline_result.verification.status == "FAILED" or pipeline_result.risk.highest_risk == "HIGH":
            doc.status = 'REVIEW'
        else:
            doc.status = 'READY'
            
        doc.current_step = 5
        
        if pipeline_result.errors:
            doc.error_message = " | ".join(pipeline_result.errors)
            
        db.session.commit()

        

    except Exception as e:
        logger.error(f"AI Processing failed for document {document_id}: {str(e)}")
        doc.status = "FAILED"
        doc.error_message = str(e)
        db.session.commit()
        raise e
