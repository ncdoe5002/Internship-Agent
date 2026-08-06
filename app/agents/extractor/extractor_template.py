from typing import List, Optional
from pydantic import BaseModel, Field


class AgmtHeaderStg(BaseModel):
    """Represents the AGMT_HEADER_STG table structure."""

    agmt_id: Optional[str] = Field(
        default=None,
        description="Unique agreement identification number or letter reference (e.g., 'IOT Discount Letter Number 5').",
    )
    sender: Optional[str] = Field(
        default=None,
        description="Originating party executing the agreement (e.g., 'Emirates Telecommunications Group Company PJSC').",
    )
    rp: Optional[str] = Field(
        default=None,
        description="Receiving party or roaming partner entity (e.g., 'Etisalat Misr', 'Orange EU Affiliates').",
    )
    tap_direction: Optional[str] = Field(
        default=None,
        description="Direction of roaming traffic covered (e.g., 'Inbound', 'Outbound', 'Bi-lateral').",
    )
    rev_no: Optional[int] = Field(
        default=None,
        description="Revision or version sequence number.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Effective start date in YYYY-MM-DD format.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Termination or end date in YYYY-MM-DD format.",
    )
    remarks: Optional[str] = Field(
        default=None,
        description="General notes or governing clauses (e.g., 'Back-to-Back IOT Discount Letter').",
    )
    currency_code: Optional[str] = Field(
        default=None,
        description="ISO currency code used for billing (e.g., 'EUR', 'USD').",
    )
    total_agmt_month: Optional[int] = Field(
        default=None,
        description="Total duration in full months (e.g., 12).",
    )


class AgmtModelsStg(BaseModel):
    """Represents high-level pricing model definitions (AGMT_MODELS_STG)."""

    model_seq: Optional[int] = Field(
        default=None, description="Sequential index of the model."
    )
    agmt_id: Optional[str] = Field(default=None, description="Parent agreement ID.")
    model_type: Optional[str] = Field(
        default=None,
        description="Pricing model type (e.g., 'Tiered', 'Flat Rate', 'Commitment', 'Incremental').",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Descriptive name (e.g., 'Orange EU Outbound Discount Model').",
    )


class AgmtMdlNormalStg(BaseModel):
    """Represents specific service charging structures and rates (AGMT_MDL_NORMAL_STG)."""

    agmt_id: Optional[str] = Field(default=None, description="Parent agreement ID.")
    model_seq: Optional[int] = Field(
        default=None, description="Sequence mapping to parent model."
    )
    rec_type: Optional[str] = Field(
        default=None,
        description="Service record type being rated (e.g., 'MOC', 'MTC', 'SMS', 'Data').",
    )
    zone_code: Optional[str] = Field(
        default=None, description="Target zone or destination group code."
    )
    rate_val: Optional[float] = Field(
        default=None,
        description="Actual numerical rate charged per unit (e.g., 0.15, 0.035, 0.022).",
    )
    rate_currency: Optional[str] = Field(
        default=None,
        description="ISO currency code for the rate (e.g., 'EUR').",
    )
    pra_rate_type: Optional[str] = Field(
        default=None,
        description="Structure type (e.g., 'Linear', 'Incremental', 'Flat').",
    )
    disc_rate_perc: Optional[float] = Field(
        default=None,
        description="Percentage discount applied to standard IOT rates.",
    )
    charge_field: Optional[str] = Field(
        default=None,
        description="Charging interval or granularity (e.g., 'per min', 'per SMS', 'per MB').",
    )


class AgmtCommitment(BaseModel):
    """Represents financial or volumetric obligations (AGMT_COMMITMENT)."""

    agmt_id: Optional[str] = Field(default=None, description="Associated agreement ID.")
    commitment_name: Optional[str] = Field(
        default=None,
        description="Descriptive commitment title (e.g., 'Etisalat Misr Send or Pay Commitment').",
    )
    commitment_type: Optional[str] = Field(
        default=None,
        description="Structure type (e.g., 'Send or Pay', 'Fixed Revenue', 'Volume Allowance').",
    )
    direction: Optional[str] = Field(
        default=None, description="'Inbound' or 'Outbound'."
    )
    amount: Optional[float] = Field(
        default=None,
        description="Financial monetary target value (e.g., 550000.0, 90000.0).",
    )
    volume_value: Optional[float] = Field(
        default=None,
        description="Volumetric allowance quantity if applicable (e.g., 800000.0, 58000000.0).",
    )
    volume_unit: Optional[str] = Field(
        default=None,
        description="Unit for volume allowance (e.g., 'min', 'SMS', 'MB').",
    )
    party_from: Optional[str] = Field(
        default=None, description="Committed party paying/sending."
    )
    party_to: Optional[str] = Field(default=None, description="Receiving party.")


class IOTAgreement(BaseModel):
    """Master container encapsulating all extracted agreement data."""

    header: Optional[AgmtHeaderStg] = Field(
        default=None,
        description="Header attributes and metadata governing the agreement.",
    )
    model: Optional[List[AgmtModelsStg]] = Field(
        default_factory=list,
        description="High-level pricing model structure definitions.",
    )
    normal_model: Optional[List[AgmtMdlNormalStg]] = Field(
        default_factory=list,
        description="Detailed service rate rules, charging increments, and currency specifications.",
    )
    commitment: Optional[List[AgmtCommitment]] = Field(
        default_factory=list,
        description="Financial or volume commitment obligations established between parties.",
    )
