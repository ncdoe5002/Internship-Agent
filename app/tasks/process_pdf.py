import logging
import os

from celery import shared_task
from flask import current_app

from ..agents.orchestrator import Orchestrator, OrchestratorInput, OrchestratorState
from ..extensions import db
from ..models.document import Document
from ..services.baseline import get_baseline_rates
from ..services.db_writer import write_extraction_to_db
from ..services.gemini import get_langchain_model

logger = logging.getLogger(__name__)


def _commit_step(doc: Document, step: int) -> None:
    """Persist current_step so the polling UI can update."""
    doc.current_step = step
    db.session.commit()


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_pdf(self, document_id: int):
    """
    Background task: read document, run orchestrator pipeline, save results.

    Pipeline steps (mirrored in processing.html UI):
      0 – Extracting tariff tables from source document
      1 – Matching line items to EDCH service catalogue  (extraction done)
      2 – Cross-checking currency, effective date & counterparties
      3 – Comparing figures against stored baseline agreement
      4 – Flagging rate changes outside historical variance  (done)
    """
    doc = Document.query.get(document_id)
    if doc is None:
        return

    doc.status = "PROCESSING"
    doc.error_message = None
    _commit_step(doc, 0)

    try:
        # ------------------------------------------------------------------
        # Resolve file path
        # doc.file_key is stored as "pdfs/<filename>" (relative to static/).
        # The upload handler saves to {root_path}/static/pdfs/.
        # ------------------------------------------------------------------
        actual_path = os.path.join(current_app.root_path, "static", doc.file_key)
        if not os.path.exists(actual_path):
            raise FileNotFoundError(f"Uploaded file not found at: {actual_path}")

        with open(actual_path, "rb") as fh:
            pdf_bytes = fh.read()

        filename = doc.filename or ""
        file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

        # Fetch baseline data for comparison (may return empty dict)
        baseline_data = get_baseline_rates(doc.partner_name or "")
        doc.baseline_data = baseline_data
        db.session.commit()

        # Initialise model and orchestrator
        model = get_langchain_model()
        orchestrator = Orchestrator(model)

        orchestrator_input = OrchestratorInput(
            pdf_bytes=pdf_bytes,
            filename=doc.file_key,
            partner_name=doc.partner_name or "Unknown",
            baseline_data=baseline_data,
            file_type=file_type,
        )

        # ------------------------------------------------------------------
        # Step 0 → 1: Extraction
        # ------------------------------------------------------------------
        _commit_step(doc, 0)
        state = OrchestratorState(input=orchestrator_input)
        updates = orchestrator._extraction_node(state)
        state = state.model_copy(update=updates)

        if state.extraction_error:
            logger.warning(f"Extraction error for doc {document_id}: {state.extraction_error}")

        _commit_step(doc, 1)

        # ------------------------------------------------------------------
        # Step 2: Verification
        # ------------------------------------------------------------------
        updates = orchestrator._verification_node(state)
        state = state.model_copy(update=updates)
        _commit_step(doc, 2)

        # ------------------------------------------------------------------
        # Step 3: Risk Assessment
        # ------------------------------------------------------------------
        updates = orchestrator._risk_node(state)
        state = state.model_copy(update=updates)
        _commit_step(doc, 3)

        # ------------------------------------------------------------------
        # Step 4: AI Notes + Combine
        # ------------------------------------------------------------------
        updates = orchestrator._ai_notes_node(state)
        state = state.model_copy(update=updates)

        combined = orchestrator._combine_results_node(state)
        result = combined.get("output") if isinstance(combined, dict) else None

        if result is None:
            raise RuntimeError("Orchestrator produced no output")

        # ------------------------------------------------------------------
        # Persist results
        # ------------------------------------------------------------------
        _commit_step(doc, 4)

        # Store full orchestrator output as JSON for audit / replay
        doc.extracted_data = result.model_dump()

        # Capture verification confidence
        if state.verification_result:
            doc.confidence_score = state.verification_result.confidence
        else:
            doc.confidence_score = 0

        # Write parsed tables to the staging DB tables
        if state.extraction_result:
            agmt_id = write_extraction_to_db(state.extraction_result, document_id)
            doc.agmt_id = agmt_id
            logger.info(f"Staged agreement data with AGMT_ID={agmt_id!r}")
        else:
            logger.warning(f"No extraction result for doc {document_id}; staging skipped")

        doc.status = "READY"
        db.session.commit()
        logger.info(f"process_pdf completed successfully for document_id={document_id}")

    except Exception as exc:
        logger.exception(f"process_pdf failed for document_id={document_id}: {exc}")
        doc.status = "FAILED"
        doc.error_message = str(exc)
        db.session.commit()
        raise self.retry(exc=exc)
