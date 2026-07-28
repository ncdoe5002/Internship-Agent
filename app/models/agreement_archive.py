from ..extensions import db
from .mixins import (
    AgmtHeaderMixin, 
    AgmtModelsMixin, 
    AgmtMdlNormalMixin, 
    AgmtCommitmentMixin
)

class ArchiveAgmtHeader(db.Model, AgmtHeaderMixin):
    __tablename__ = "archive_agmt_header"
    __table_args__ = {"schema": "archive"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Links to the MNO table just like production, so you can easily pull 
    # all historical contracts for a specific MNO in the future.
    mno_id = db.Column(db.Integer, db.ForeignKey("mnos.id"), nullable=True) 

    # Clean relationships to child tables via surrogate ID
    models = db.relationship("ArchiveAgmtModels", backref="header", cascade="all, delete-orphan", lazy=True)
    commitments = db.relationship("ArchiveAgmtCommitment", backref="header", cascade="all, delete-orphan", lazy=True)


class ArchiveAgmtModels(db.Model, AgmtModelsMixin):
    __tablename__ = "archive_agmt_models"
    __table_args__ = {"schema": "archive"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("archive.archive_agmt_header.id"), nullable=False)

    normal_rates = db.relationship("ArchiveAgmtMdlNormal", backref="model", cascade="all, delete-orphan", lazy=True)


class ArchiveAgmtMdlNormal(db.Model, AgmtMdlNormalMixin):
    __tablename__ = "archive_agmt_mdl_normal"
    __table_args__ = {"schema": "archive"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    model_id = db.Column(db.Integer, db.ForeignKey("archive.archive_agmt_models.id"), nullable=False)


class ArchiveAgmtCommitment(db.Model, AgmtCommitmentMixin):
    __tablename__ = "archive_agmt_commitment"
    __table_args__ = {"schema": "archive"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    header_id = db.Column(db.Integer, db.ForeignKey("archive.archive_agmt_header.id"), nullable=False)