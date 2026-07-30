from ..extensions import db
from .mixins import (
    AgmtHeaderMixin, 
    AgmtModelsMixin, 
    AgmtMdlNormalMixin, 
    AgmtCommitmentMixin
)

# --- TEMP SCHEMA (Staging Sandbox) ---
class TempAgmtHeader(db.Model, AgmtHeaderMixin):
    __tablename__ = "temp_agmt_header"
    __table_args__ = {"schema": "temp"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id")) # Links to your Document model[cite: 3]
    
    models = db.relationship("TempAgmtModels", backref="header", cascade="all, delete-orphan")
    commitments = db.relationship("TempAgmtCommitment", backref="header", cascade="all, delete-orphan")

class TempAgmtModels(db.Model, AgmtModelsMixin):
    __tablename__ = "temp_agmt_models"
    __table_args__ = {"schema": "temp"}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("temp.temp_agmt_header.id"), nullable=False)
    normal_rates = db.relationship("TempAgmtMdlNormal", backref="model", cascade="all, delete-orphan")

class TempAgmtMdlNormal(db.Model, AgmtMdlNormalMixin):
    __tablename__ = "temp_agmt_mdl_normal"
    __table_args__ = {"schema": "temp"}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    model_id = db.Column(db.Integer, db.ForeignKey("temp.temp_agmt_models.id"), nullable=False)

class TempAgmtCommitment(db.Model, AgmtCommitmentMixin):
    __tablename__ = "temp_agmt_commitment"
    __table_args__ = {"schema": "temp"}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("temp.temp_agmt_header.id"), nullable=False)

# --- ARCHIVE SCHEMA (Cold Storage) ---
# (Repeat the exact same pattern as Temp, but change "temp" to "archive")
# Archive tables DO NOT have the unique RP constraint so you can store revisions safely.