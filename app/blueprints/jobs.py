import logging
from celery import shared_task
from app.extensions import db
from app.models.document import Document
from app.services.extractors import extract_roaming_agreement
from app.services.db_mapper import save_extracted_tables_to_db

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_contract_task(self, document_id: int, contract_text: str):
    doc = Document.query.get(document_id)
    
    try:
        # 2. Update UI: Step 1 & 2 (Extracting & Matching)
        if doc:
            doc.current_step = 2
            db.session.commit()

        # Run the LLM extraction
        extracted_json = extract_roaming_agreement(contract_text)

        # 3. Update UI: Step 3 & 4 (Cross-checking & Comparing)
        if doc:
            doc.current_step = 4
            db.session.commit()

        # Save to staging tables
        save_extracted_tables_to_db(document_id, extracted_json)
        
        # 4. THE MAGIC BULLET: Tell the UI it's completely finished
        if doc:
            doc.status = 'READY'
            doc.current_step = 5
            db.session.commit()

    except Exception as e:
        logger.error(f"AI Processing failed for document {document_id}: {str(e)}")
        
        # Capture error directly into the Document model for the UI
        if doc:
            doc.status = "FAILED"
            doc.error_message = str(e)
            db.session.commit()
            
        raise e
