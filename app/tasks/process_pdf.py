from celery import shared_task
from flask import current_app

from ..extensions import db
from ..models.document import Document
from ..services.gemini import extract_table_data
from ..services.storage import read_pdf


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_pdf(self, document_id: int):
    """Background task: read PDF, call Gemini, save result, update status."""
    doc = Document.query.get(document_id)
    if doc is None:
        return

    doc.status = "PROCESSING"
    db.session.commit()

    try:
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        pdf_bytes = read_pdf(doc.file_key, upload_folder)
        result = extract_table_data(pdf_bytes)
        doc.extracted_data = result.model_dump()
        doc.status = "READY"
    except Exception as exc:
        doc.status = "FAILED"
        db.session.commit()
        raise self.retry(exc=exc)

    db.session.commit()
