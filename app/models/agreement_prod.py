from ..extensions import db
from .mixins import (
    AgmtHeaderMixin, 
    AgmtModelsMixin, 
    AgmtMdlNormalMixin, 
    AgmtCommitmentMixin
)

class ProdAgmtHeader(db.Model, AgmtHeaderMixin):
    __tablename__ = "prod_agmt_header"
    __table_args__ = (
        # Enforces ONE active agreement per Partner (RP) in Production
        db.UniqueConstraint("RP", name="uq_prod_active_rp"),
        {"schema": "prod"}
    )

    # Surrogate Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Link to your existing MNO table[cite: 4]
    mno_id = db.Column(db.Integer, db.ForeignKey("mnos.id"), nullable=True) 

    # Clean relationships to child tables via surrogate ID
    models = db.relationship("ProdAgmtModels", backref="header", cascade="all, delete-orphan", lazy=True)
    commitments = db.relationship("ProdAgmtCommitment", backref="header", cascade="all, delete-orphan", lazy=True)

class ProdAgmtModels(db.Model, AgmtModelsMixin):
    __tablename__ = "prod_agmt_models"
    __table_args__ = {"schema": "prod"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("prod.prod_agmt_header.id"), nullable=False)

    normal_rates = db.relationship("ProdAgmtMdlNormal", backref="model", cascade="all, delete-orphan", lazy=True)

class ProdAgmtMdlNormal(db.Model, AgmtMdlNormalMixin):
    __tablename__ = "prod_agmt_mdl_normal"
    __table_args__ = {"schema": "prod"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Notice we link directly to the Model ID, not the Header ID
    model_id = db.Column(db.Integer, db.ForeignKey("prod.prod_agmt_models.id"), nullable=False)

class ProdAgmtCommitment(db.Model, AgmtCommitmentMixin):
    __tablename__ = "prod_agmt_commitment"
    __table_args__ = {"schema": "prod"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("prod.prod_agmt_header.id"), nullable=False)