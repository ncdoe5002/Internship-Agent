from ..extensions import db


class ProductionRecord(db.Model):
    __tablename__ = "production_records"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False, unique=True
    )
    data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
