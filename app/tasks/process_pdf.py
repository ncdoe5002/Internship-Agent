from celery import shared_task
from flask import current_app

from ..agents.orchestrator import Orchestrator, OrchestratorInput
from ..extensions import db
from ..models.document import Document
from ..services.gemini import get_langchain_model
from ..services.storage import read_pdf


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_pdf(self, document_id: int):
    """
    Background task: read PDF, run orchestrator workflow, save result, update status.
    
    The orchestrator coordinates ExtractionAgent, VerificationAgent, and RiskAgent
    using LangGraph for parallel execution and graceful error handling.
    """
    doc = Document.query.get(document_id)
    if doc is None:
        return

    doc.status = "PROCESSING"
    db.session.commit()

    try:
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        pdf_bytes = read_pdf(doc.file_key, upload_folder)
        
        # Initialize LangChain-compatible model
        model = get_langchain_model()
        
        # Initialize orchestrator
        orchestrator = Orchestrator(model)
        
        # Prepare orchestrator input
        orchestrator_input = OrchestratorInput(
            pdf_bytes=pdf_bytes,
            filename=doc.file_key,
            partner_name=doc.partner_name or "Unknown",
            baseline_data=doc.baseline_data
        )
        
        # Run orchestrator workflow
        result = orchestrator.run(orchestrator_input)
        
        # Save combined results to document
        doc.extracted_data = result.model_dump()
        
        # Set status based on errors
        if result.errors:
            # Partial success - some agents failed
            doc.status = "READY"  # Still mark as ready for manual review
        else:
            doc.status = "READY"
            
    except Exception as exc:
        doc.status = "FAILED"
        db.session.commit()
        raise self.retry(exc=exc)

    db.session.commit()
