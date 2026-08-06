import os
import logging
from typing import Any, cast
from flask import current_app
from celery import shared_task
from app.extensions import db

from app.models.document import Document
from app.agents.extractor.docling_extractor import get_contents
from app.services.db_mapper import get_baseline_data
from app.agents.orchestrator import Orchestrator, OrchestratorInput

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_contract_task(self, document_id: int, contract_text: str):
    doc = Document.query.get(document_id)
    if not doc:
        logger.error(
            f"Document with ID {document_id} not found in database. Aborting task."
        )
        return

    try:
        doc.current_step = 2
        db.session.commit()

        file_path = os.path.join(current_app.root_path, "static", doc.file_key)

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
            elif hasattr(obj, "dict"):  # Pydantic v1
                return obj.dict()
            return obj if isinstance(obj, dict) else {}

        # -------------------------------------------------------------
        # SAVE DIRECTLY TO DOCUMENT.EXTRACTED_DATA (BYPASS TEMP DB)
        # -------------------------------------------------------------
        payload = {
            "header": to_dict(header),
            "model": to_dict(model),
            "normal_model": to_dict(normal_model),
            "commitment": to_dict(commitment),
        }

        doc.extracted_data = payload
        doc.agmt_id = payload.get("header", {}).get("agmt_id")
        
        # Save baseline data for comparison
        baseline_tables = get_baseline_data(doc.partner_name)
        doc.baseline_data = baseline_tables

        # Run Verification & Risk Pipeline
        orchestrator = Orchestrator()
        pipeline_input = OrchestratorInput(
            pdf_bytes=pdf_bytes,
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
            doc.status = "READY"

        doc.current_step = 5
        if pipeline_result.errors:
            doc.error_message = " | ".join(pipeline_result.errors)

    except Exception as e:
        logger.error(f"AI Processing failed for document {document_id}: {str(e)}")
        db.session.rollback()  # Clear broken session state
        doc = Document.query.get(document_id)
        if doc:
            doc.status = "FAILED"
            doc.error_message = str(e)
            db.session.commit()
        raise e
