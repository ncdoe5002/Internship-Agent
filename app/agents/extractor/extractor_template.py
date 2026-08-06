from typing import List, Optional
from pydantic import BaseModel, Field

from typing import Optional
from pydantic import BaseModel, Field


class AgmtHeaderStg(BaseModel):
    """
    Represents the AGMT_HEADER_STG table structure.

    Extract values only if explicitly available in the document.
    Do not infer missing values. Return null when information is absent.
    """

    agmt_id: Optional[str] = Field(
        default=None,
        description="Unique agreement identifier or agreement reference number.",
    )

    sender: Optional[str] = Field(
        default=None, description="Party sending the agreement or originating operator."
    )

    rp: Optional[str] = Field(
        default=None,
        description="Receiving party (RP) or partner operator involved in the agreement.",
    )

    tap_direction: Optional[str] = Field(
        default=None,
        description="TAP direction indicating inbound or outbound roaming traffic.",
    )

    rev_no: Optional[int] = Field(
        default=None, description="Agreement revision number."
    )

    start_date: Optional[str] = Field(
        default=None,
        description="Agreement effective start date. Preserve document format if exact conversion is not possible.",
    )

    end_date: Optional[str] = Field(
        default=None, description="Agreement termination or expiry date."
    )

    remarks: Optional[str] = Field(
        default=None, description="General remarks or notes related to the agreement."
    )

    data_level: Optional[str] = Field(
        default=None, description="Data processing or agreement classification level."
    )

    invoice_amt_type: Optional[str] = Field(
        default=None,
        description="Invoice amount calculation type or billing amount category.",
    )

    user_act_id: Optional[str] = Field(
        default=None,
        description="User ID responsible for agreement creation or action.",
    )

    created_date: Optional[str] = Field(
        default=None, description="Date when the agreement record was created."
    )

    currency_code: Optional[str] = Field(
        default=None,
        description="Currency code used for agreement transactions (example: USD, AED, EUR).",
    )

    auto_renewal: Optional[bool] = Field(
        default=None,
        description="Whether the agreement automatically renews. Extract only explicit yes/no values.",
    )

    is_group_rp: Optional[bool] = Field(
        default=None,
        description="Indicates whether the receiving party belongs to a group.",
    )

    agmt_status: Optional[str] = Field(
        default=None,
        description="Current agreement status such as active, expired, pending, or terminated.",
    )

    total_agmt_month: Optional[int] = Field(
        default=None, description="Total agreement duration in months."
    )

    is_rerating_reqd: Optional[bool] = Field(
        default=None, description="Indicates whether rerating is required."
    )

    gprs_rule: Optional[str] = Field(
        default=None,
        description="GPRS charging or usage rule defined in the agreement.",
    )

    gprs_limit: Optional[float] = Field(
        default=None, description="GPRS limit or threshold value."
    )

    baseline_rule: Optional[str] = Field(
        default=None,
        description="Baseline calculation rule defined for commitments or billing.",
    )

    baseline_base_field: Optional[str] = Field(
        default=None,
        description="Field used as the base value for baseline calculation.",
    )

    baseline_value: Optional[float] = Field(
        default=None, description="Numeric baseline threshold or committed value."
    )

    commit_rule: Optional[str] = Field(
        default=None, description="Commitment calculation rule."
    )

    commit_base_field: Optional[str] = Field(
        default=None, description="Field used as the basis for commitment calculation."
    )

    commit_value: Optional[float] = Field(
        default=None, description="Numeric commitment value."
    )

    is_group_client: Optional[bool] = Field(
        default=None, description="Indicates whether client belongs to a group."
    )

    parent_agmt_id: Optional[str] = Field(
        default=None,
        description="Parent agreement identifier if this agreement is derived from another agreement.",
    )

    regen_required: Optional[bool] = Field(
        default=None, description="Indicates whether regeneration is required."
    )

    is_tap_level_agmt: Optional[bool] = Field(
        default=None, description="Indicates whether agreement is defined at TAP level."
    )

    is_partial_client: Optional[bool] = Field(
        default=None, description="Indicates whether partial client processing applies."
    )

    is_partial_rp: Optional[bool] = Field(
        default=None,
        description="Indicates whether partial receiving party processing applies.",
    )

    baseline_level: Optional[str] = Field(
        default=None, description="Level at which baseline calculation is applied."
    )

    master_agmt_id: Optional[str] = Field(
        default=None,
        description="Master agreement identifier associated with this agreement.",
    )

    modified_user: Optional[str] = Field(
        default=None, description="User who last modified the agreement."
    )

    modified_date: Optional[str] = Field(
        default=None, description="Date of last modification."
    )

    agmt_type: Optional[str] = Field(
        default=None, description="Agreement type or category."
    )

    bulk_id: Optional[str] = Field(
        default=None, description="Bulk processing identifier if available."
    )

    is_baseline_applicable: Optional[bool] = Field(
        default=None,
        description="Indicates whether baseline rules apply to the agreement.",
    )

    agmt_level_rc_type: Optional[str] = Field(
        default=None, description="Agreement level recurring charge type."
    )

    spl_remarks: Optional[str] = Field(
        default=None,
        description="Special remarks or exceptions mentioned in the agreement.",
    )

    currency_agmt: Optional[str] = Field(
        default=None,
        description="Currency specified specifically for agreement calculations.",
    )

    imsi_activation_type: Optional[str] = Field(
        default=None, description="Type of IMSI activation."
    )

    imsi_activation_criteria: Optional[str] = Field(
        default=None, description="Criteria required for IMSI activation."
    )

    rap_chrg: Optional[float] = Field(default=None, description="RAP charging value.")

    rap_vol: Optional[float] = Field(
        default=None, description="RAP volume value or threshold."
    )

    exchange_rate_type: Optional[str] = Field(
        default=None, description="Exchange rate calculation type."
    )

    agmt_level_rc_var_type: Optional[str] = Field(
        default=None, description="Agreement level recurring charge variable type."
    )

    agmt_doc_status: Optional[str] = Field(
        default=None, description="Agreement document approval or processing status."
    )

    agmt_nego_status: Optional[str] = Field(
        default=None, description="Agreement negotiation status."
    )

    inc_in_accrl_rpt: Optional[bool] = Field(
        default=None, description="Whether agreement is included in accrual reports."
    )

    is_m2m_applcbl: Optional[bool] = Field(
        default=None, description="Whether machine-to-machine (M2M) processing applies."
    )

    agmt_verified: Optional[bool] = Field(
        default=None, description="Whether agreement has been verified."
    )

    agmt_verified_by: Optional[str] = Field(
        default=None, description="Person or user who verified the agreement."
    )

    agmt_verified_date: Optional[str] = Field(
        default=None, description="Date when agreement verification occurred."
    )


class AgmtModelsStg(BaseModel):
    """Represents the AGMT_MODELS_STG table structure."""

    model_seq: Optional[int] = None
    agmt_id: Optional[str] = None
    model_type: Optional[str] = None
    model_name: Optional[str] = None


class AgmtMdlNormalStg(BaseModel):
    """Represents the AGMT_MDL_NORMAL_STG table structure."""

    agmt_id: Optional[str] = None
    model_seq: Optional[int] = None
    rec_type: Optional[str] = None
    zone_code: Optional[str] = None
    rate_currency: Optional[str] = None
    pra_rate_type: Optional[str] = None
    disc_rate_perc: Optional[float] = None
    charge_include_tax: Optional[bool] = None
    charge_field: Optional[str] = None


class AgmtCommitment(BaseModel):
    """Represents the AGMT_COMMITMENT table structure."""

    agmt_id: Optional[str] = None
    commitment_name: Optional[str] = None
    commitment_type: Optional[str] = None
    direction: Optional[str] = None
    amount: Optional[float] = None
    capture_rate_pct: Optional[float] = None
    party_from: Optional[str] = None
    party_to: Optional[str] = None


class IOTAgreement(BaseModel):
    header: Optional[AgmtHeaderStg] = None
    model: list[AgmtModelsStg] = []
    normal_model: list[AgmtMdlNormalStg] = []
    commitment: list[AgmtCommitment] = []
