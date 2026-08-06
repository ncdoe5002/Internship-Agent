import logging
from typing import Any, List
from app.extensions import db
from app.models.document import Document
from app.models.mno import Mno
from app.models.agreement_prod import ProdAgmtHeader, ProdAgmtMdlNormal, ProdAgmtModels

logger = logging.getLogger(__name__)


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