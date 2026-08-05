import logging
from typing import Any, List
from app.extensions import db
from app.models.document import Document
from app.models.agreement_temp import (
    TempAgmtHeader, 
    TempAgmtModels, 
    TempAgmtMdlNormal, 
    TempAgmtCommitment
)
from app.models.mno import Mno
from app.models.agreement_prod import ProdAgmtHeader, ProdAgmtMdlNormal, ProdAgmtModels

logger = logging.getLogger(__name__)


def _to_list(item: Any) -> List[Any]:
    """Helper to ensure input is always handled as a list."""
    if item is None:
        return []
    if isinstance(item, list):
        return item
    return [item]


def _populate_record(sqlalchemy_record: Any, data: Any):
    """
    Populates SQLAlchemy record fields from a Pydantic model or dictionary.
    Handles case-insensitive field matching (e.g. sender -> SENDER).
    """
    if data is None:
        return

    if hasattr(data, "model_dump"):
        data_dict = data.model_dump()
    elif isinstance(data, dict):
        data_dict = data
    else:
        return

    for key, value in data_dict.items():
        if value is None or value == "" or value == "null":
            continue

        # Check exact, uppercase, and lowercase attribute matches on SQLAlchemy model
        target_attr = None
        if hasattr(sqlalchemy_record, key):
            target_attr = key
        elif hasattr(sqlalchemy_record, key.upper()):
            target_attr = key.upper()
        elif hasattr(sqlalchemy_record, key.lower()):
            target_attr = key.lower()

        if target_attr:
            setattr(sqlalchemy_record, target_attr, value)


def save_extracted_tables_to_db(header: Any, model: Any, normal_model: Any, commitment: Any, document_id: int):
    """
    Saves the extracted Pydantic objects from docling_extractor into SQLAlchemy staging tables.
    """
    doc = Document.query.get(document_id)
    if not doc:
        logger.error(f"Document ID {document_id} not found in database.")
        return

    # 1. Save Header
    current_header = TempAgmtHeader()
    current_header.document_id = document_id
    _populate_record(current_header, header)
    
    db.session.add(current_header)
    db.session.flush()  # Generate current_header.id for surrogate keys

    # 2. Save Models
    models_list = _to_list(model)
    model_mapping = {}  # Maps MODEL_SEQ string -> database model.id

    for m in models_list:
        db_model = TempAgmtModels()
        db_model.header_id = current_header.id
        _populate_record(db_model, m)
        
        db.session.add(db_model)
        db.session.flush()

        # Track sequence for linking child rate records
        m_dict = m.model_dump() if hasattr(m, "model_dump") else (m if isinstance(m, dict) else {})
        seq = m_dict.get("model_seq") or m_dict.get("MODEL_SEQ") or "1"
        model_mapping[str(seq)] = db_model.id

    # 3. Save Normal Models / Rate Details
    rates_list = _to_list(normal_model)
    for r in rates_list:
        db_rate = TempAgmtMdlNormal()
        
        r_dict = r.model_dump() if hasattr(r, "model_dump") else (r if isinstance(r, dict) else {})
        ai_seq = str(r_dict.get("model_seq") or r_dict.get("MODEL_SEQ") or "1")
        
        # Link to parent model ID
        db_rate.model_id = model_mapping.get(ai_seq) or (list(model_mapping.values())[0] if model_mapping else None)
        
        _populate_record(db_rate, r)

        # Sanitize numeric fields
        if hasattr(db_rate, 'CHARGE_FIELD') and db_rate.CHARGE_FIELD is not None:
            try:
                db_rate.CHARGE_FIELD = float(db_rate.CHARGE_FIELD)
            except (ValueError, TypeError):
                db_rate.CHARGE_FIELD = 0.0

        db.session.add(db_rate)

    # 4. Save Commitments
    commitments_list = _to_list(commitment)
    for c in commitments_list:
        db_comm = TempAgmtCommitment()
        db_comm.header_id = current_header.id
        _populate_record(db_comm, c)

        # Sanitize numeric fields
        if hasattr(db_comm, 'AMOUNT') and db_comm.AMOUNT is not None:
            try:
                db_comm.AMOUNT = float(db_comm.AMOUNT)
            except (ValueError, TypeError):
                db_comm.AMOUNT = 0.0

        db.session.add(db_comm)

    try:
        db.session.commit()
        logger.info(f"Successfully saved all extracted objects for document {document_id} to DB.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database insertion failed for document {document_id}. Session rolled back. Error: {str(e)}")
        raise e


def get_baseline_data(partner_name: str) -> dict | None:
    """Fetches production baseline data for an MNO and formats it for the Orchestrator."""
    mno = Mno.query.filter_by(name=partner_name).first()
    if not mno:
        return None
        
    prod_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
    if not prod_header:
        return None
        
    prod_models = ProdAgmtModels.query.filter_by(header_id=prod_header.id).all()
    model_ids = [m.id for m in prod_models]
    prod_rates = ProdAgmtMdlNormal.query.filter(ProdAgmtMdlNormal.model_id.in_(model_ids)).all()
    
    rows = []
    for rate in prod_rates:
        rows.append([
            getattr(rate, 'REC_TYPE', ''),
            getattr(rate, 'ZONE_CODE', ''),
            str(getattr(rate, 'CHARGE_FIELD', 0.0))
        ])
        
    return {
        "tables": [{
            "title": "Baseline Rates",
            "headers": ["CATEGORY", "ZONE", "RATE"],
            "rows": rows
        }]
    }