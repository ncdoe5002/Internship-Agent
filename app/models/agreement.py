# app/models/agreement.py

from ..extensions import db


class AgmtHeaderStg(db.Model):
    """Agreement header staging table. One row per agreement."""

    __tablename__ = "AGMT_HEADER_STG"

    AGMT_ID = db.Column(db.String(50), primary_key=True)
    SENDER = db.Column(db.String(100))
    RP = db.Column(db.String(100))
    TAP_DIRECTION = db.Column(db.String(20))
    REV_NO = db.Column(db.Integer)
    START_DATE = db.Column(db.Date)
    END_DATE = db.Column(db.Date)
    REMARKS = db.Column(db.Text)
    DATA_LEVEL = db.Column(db.String(20))
    INVOICE_AMT_TYPE = db.Column(db.String(20))
    USER_ACT_ID = db.Column(db.String(50))
    CREATED_DATE = db.Column(db.DateTime)
    CURRENCY_CODE = db.Column(db.String(3))
    AUTO_RENEWAL = db.Column(db.Boolean)
    IS_GROUP_RP = db.Column(db.Boolean)
    AGMT_STATUS = db.Column(db.String(20))
    TOTAL_AGMT_MONTH = db.Column(db.Integer)
    IS_RERATING_REQD = db.Column(db.Boolean)
    GPRS_RULE = db.Column(db.String(50))
    GPRS_LIMIT = db.Column(db.Numeric(18, 4))
    BASELINE_RULE = db.Column(db.String(50))
    BASELINE_BASE_FIELD = db.Column(db.String(50))
    BASELINE_VALUE = db.Column(db.Numeric(18, 4))
    COMMIT_RULE = db.Column(db.String(50))
    COMMIT_BASE_FIELD = db.Column(db.String(50))
    COMMIT_VALUE = db.Column(db.Numeric(18, 4))
    IS_GROUP_CLIENT = db.Column(db.Boolean)
    PARENT_AGMT_ID = db.Column(db.String(50))
    REGEN_REQUIRED = db.Column(db.Boolean)
    IS_TAP_LEVEL_AGMT = db.Column(db.Boolean)
    IS_PARTIAL_CLIENT = db.Column(db.Boolean)
    IS_PARTIAL_RP = db.Column(db.Boolean)
    BASELINE_LEVEL = db.Column(db.String(20))
    MASTER_AGMT_ID = db.Column(db.String(50))
    MODIFIED_USER = db.Column(db.String(50))
    MODIFIED_DATE = db.Column(db.DateTime)
    AGMT_TYPE = db.Column(db.String(20))
    BULK_ID = db.Column(db.String(50))
    IS_BASELINE_APPLICABLE = db.Column(db.Boolean)
    AGMT_LEVEL_RC_TYPE = db.Column(db.String(20))
    SPL_REMARKS = db.Column(db.Text)
    CURRENCY_AGMT = db.Column(db.String(3))
    IMSI_ACTIVATION_TYPE = db.Column(db.String(20))
    IMSI_ACTIVATION_CRITERIA = db.Column(db.String(100))
    RAP_CHRG = db.Column(db.Numeric(18, 4))
    RAP_VOL = db.Column(db.Numeric(18, 4))
    EXCHANGE_RATE_TYPE = db.Column(db.String(20))
    AGMT_LEVEL_RC_VAR_TYPE = db.Column(db.String(20))
    AGMT_DOC_STATUS = db.Column(db.String(20))
    AGMT_NEGO_STATUS = db.Column(db.String(20))
    INC_IN_ACCRL_RPT = db.Column(db.Boolean)
    IS_M2M_APPLCBL = db.Column(db.Boolean)
    AGMT_VERIFIED = db.Column(db.Boolean)
    AGMT_VERIFIED_BY = db.Column(db.String(50))
    AGMT_VERIFIED_DATE = db.Column(db.DateTime)
    HAS_UNRESOLVED_CONFLICT = db.Column(db.Boolean, default=False)

    models = db.relationship("AgmtModelsStg", backref="agreement", lazy=True)
    commitments = db.relationship("AgmtCommitment", backref="agreement", lazy=True)


class AgmtModelsStg(db.Model):
    """Links an agreement to its rate models.

    Uses a surrogate autoincrement ``id`` as the primary key so that
    multiple documents can each have a MODEL_SEQ starting at 1 without
    colliding.  A unique constraint on (AGMT_ID, MODEL_SEQ) enforces
    logical uniqueness within each agreement.
    """

    __tablename__ = "AGMT_MODELS_STG"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    MODEL_SEQ = db.Column(db.Integer, nullable=False)
    MODEL_TYPE = db.Column(db.String(20))
    AGMT_ID = db.Column(db.String(50), db.ForeignKey("AGMT_HEADER_STG.AGMT_ID"))
    MODEL_NAME = db.Column(db.String(100))

    __table_args__ = (
        db.UniqueConstraint("AGMT_ID", "MODEL_SEQ", name="uq_agmt_model_seq"),
    )

    # Relationship via AGMT_ID + MODEL_SEQ (no DB-level FK needed on the rate side)
    normal_rates = db.relationship(
        "AgmtMdlNormalStg",
        primaryjoin=(
            "and_(AgmtModelsStg.AGMT_ID == foreign(AgmtMdlNormalStg.AGMT_ID),"
            " AgmtModelsStg.MODEL_SEQ == foreign(AgmtMdlNormalStg.MODEL_SEQ))"
        ),
        lazy=True,
        viewonly=True,
    )


class AgmtMdlNormalStg(db.Model):
    """Normal rate model rows: per-charge-type rate details for a model."""

    __tablename__ = "AGMT_MDL_NORMAL_STG"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    AGMT_ID = db.Column(db.String(50), db.ForeignKey("AGMT_HEADER_STG.AGMT_ID"))
    REC_TYPE = db.Column(db.String(20))
    ZONE_CODE = db.Column(db.String(20))
    RATE_CURRENCY = db.Column(db.String(3))
    PRA_RATE_TYPE = db.Column(db.String(20))
    DISC_RATE_PERC = db.Column(db.Numeric(9, 4))
    CHARGE_INCLUDE_TAX = db.Column(db.Boolean)
    CHARGE_FIELD = db.Column(db.Numeric(50))
    # Logical FK to AgmtModelsStg(AGMT_ID, MODEL_SEQ) — no DB-level FK constraint
    # because MODEL_SEQ is no longer the sole primary key on AGMT_MODELS_STG.
    MODEL_SEQ = db.Column(db.Integer)


class AgmtCommitment(db.Model):
    """Send-or-pay / traffic allowance commitments per agreement."""

    __tablename__ = "AGMT_COMMITMENT"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    AGMT_ID = db.Column(db.String(50), db.ForeignKey("AGMT_HEADER_STG.AGMT_ID"))
    COMMITMENT_NAME = db.Column(db.String(100))
    COMMITMENT_TYPE = db.Column(db.String(50))
    DIRECTION = db.Column(db.String(20))
    AMOUNT = db.Column(db.Numeric(18, 4))
    CAPTURE_RATE_PCT = db.Column(db.Numeric(9, 4))
    PARTY_FROM = db.Column(db.String(100))
    PARTY_TO = db.Column(db.String(100))
    SOURCE_TYPE = db.Column(db.String(20))       # "PROSE" or "TABLE"
    CONFLICT_FLAG = db.Column(db.Boolean, default=False)
    CONFLICT_NOTE = db.Column(db.Text)
