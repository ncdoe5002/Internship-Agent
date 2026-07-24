from ..extensions import db


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_key = db.Column(db.String(512), nullable=False)  # path or S3 key
    status = db.Column(db.String(20), nullable=False, default="PENDING")
    extracted_data = db.Column(db.JSON, nullable=True)
    partner_name = db.Column(db.String(255), nullable=True)   # Partner/Operator name
    baseline_data = db.Column(db.JSON, nullable=True)         # Baseline tariff data for comparison

    # Pipeline progress & results
    current_step = db.Column(db.Integer, nullable=True, default=0)
    confidence_score = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    agmt_id = db.Column(db.String(50), nullable=True)         # AGMT_ID of staging records for this doc

    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    audit_logs = db.relationship("AuditLog", backref="document", lazy=True)
    production_record = db.relationship(
        "ProductionRecord", backref="document", uselist=False
    )
