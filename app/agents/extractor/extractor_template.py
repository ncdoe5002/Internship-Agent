# app/agents/extractor/extractor_template.py
from typing import List, Optional
from pydantic import BaseModel, Field


class AgmtHeaderStg(BaseModel):
    """Agreement header staging table containing all DB columns."""

    agmt_id: Optional[str] = Field(
        default=None,
        description="Unique agreement identification number (e.g., 'IOT-2024-05').",
    )
    sender: Optional[str] = Field(
        default=None, description="Originating party executing the agreement."
    )
    rp: Optional[str] = Field(
        default=None, description="Receiving party or roaming partner entity."
    )
    tap_direction: Optional[str] = Field(
        default=None,
        description="Direction of roaming traffic (e.g., 'Inbound', 'Outbound').",
    )
    rev_no: Optional[int] = Field(default=None)
    start_date: Optional[str] = Field(
        default=None, description="Effective start date in YYYY-MM-DD format."
    )
    end_date: Optional[str] = Field(
        default=None, description="Termination or end date in YYYY-MM-DD format."
    )
    remarks: Optional[str] = Field(
        default=None, description="General notes or governing clauses."
    )
    data_level: Optional[str] = Field(default=None)
    invoice_amt_type: Optional[str] = Field(default=None)
    user_act_id: Optional[str] = Field(default=None)
    created_date: Optional[str] = Field(default=None)
    currency_code: Optional[str] = Field(
        default=None, description="ISO currency code (e.g., 'EUR', 'USD')."
    )
    auto_renewal: Optional[bool] = Field(default=None)
    is_group_rp: Optional[bool] = Field(default=None)
    agmt_status: Optional[str] = Field(default=None)
    total_agmt_month: Optional[int] = Field(
        default=None, description="Total duration in full months."
    )
    is_rerating_reqd: Optional[bool] = Field(default=None)
    gprs_rule: Optional[str] = Field(default=None)
    gprs_limit: Optional[float] = Field(default=None)
    baseline_rule: Optional[str] = Field(default=None)
    baseline_base_field: Optional[str] = Field(default=None)
    baseline_value: Optional[float] = Field(default=None)
    commit_rule: Optional[str] = Field(default=None)
    commit_base_field: Optional[str] = Field(default=None)
    commit_value: Optional[float] = Field(default=None)
    is_group_client: Optional[bool] = Field(default=None)
    parent_agmt_id: Optional[str] = Field(default=None)
    regen_required: Optional[bool] = Field(default=None)
    is_tap_level_agmt: Optional[bool] = Field(default=None)
    is_partial_client: Optional[bool] = Field(default=None)
    is_partial_rp: Optional[bool] = Field(default=None)
    baseline_level: Optional[str] = Field(default=None)
    master_agmt_id: Optional[str] = Field(default=None)
    modified_user: Optional[str] = Field(default=None)
    modified_date: Optional[str] = Field(default=None)
    agmt_type: Optional[str] = Field(default=None)
    bulk_id: Optional[str] = Field(default=None)
    is_baseline_applicable: Optional[bool] = Field(default=None)
    agmt_level_rc_type: Optional[str] = Field(default=None)
    spl_remarks: Optional[str] = Field(default=None)
    currency_agmt: Optional[str] = Field(default=None)
    imsi_activation_type: Optional[str] = Field(default=None)
    imsi_activation_criteria: Optional[str] = Field(default=None)
    rap_chrg: Optional[float] = Field(default=None)
    rap_vol: Optional[float] = Field(default=None)
    exchange_rate_type: Optional[str] = Field(default=None)
    agmt_level_rc_var_type: Optional[str] = Field(default=None)
    agmt_doc_status: Optional[str] = Field(default=None)
    agmt_nego_status: Optional[str] = Field(default=None)
    inc_in_accrl_rpt: Optional[bool] = Field(default=None)
    is_m2m_applcbl: Optional[bool] = Field(default=None)
    agmt_verified: Optional[bool] = Field(default=None)
    agmt_verified_by: Optional[str] = Field(default=None)
    agmt_verified_date: Optional[str] = Field(default=None)
    has_unresolved_conflict: Optional[bool] = Field(default=None)


class AgmtModelsStg(BaseModel):
    """Links an agreement to its rate models."""

    model_seq: Optional[int] = Field(
        default=None, description="Sequential index of the model."
    )
    model_type: Optional[str] = Field(
        default=None, description="Pricing model type (e.g., 'Tiered', 'Flat Rate')."
    )
    model_name: Optional[str] = Field(
        default=None, description="Descriptive name of the model."
    )
    agmt_id: Optional[str] = Field(default=None, description="Parent agreement ID.")


class AgmtMdlNormalStg(BaseModel):
    """Normal rate model rows containing all DB columns."""

    rec_type: Optional[str] = Field(
        default=None, description="Service record type (e.g., 'MOC', 'SMS', 'Data')."
    )
    zone_code: Optional[str] = Field(
        default=None, description="Target zone or destination group code."
    )
    rate_currency: Optional[str] = Field(
        default=None, description="ISO currency code for the rate."
    )
    pra_rate_type: Optional[str] = Field(
        default=None,
        description="Structure type (e.g., 'Linear', 'Incremental', 'Flat').",
    )
    disc_rate_perc: Optional[float] = Field(
        default=None, description="Percentage discount applied to standard IOT rates."
    )
    charge_include_tax: Optional[bool] = Field(default=None)
    charge_field: Optional[float] = Field(
        default=None,
        description="Actual numerical rate charged per unit (e.g., 0.15, 0.035).",
    )
    model_seq: Optional[int] = Field(
        default=None, description="Sequence mapping to parent model."
    )
    agmt_id: Optional[str] = Field(default=None, description="Parent agreement ID.")


class AgmtCommitment(BaseModel):
    """Send-or-pay / traffic allowance commitments per agreement."""

    commitment_name: Optional[str] = Field(
        default=None, description="Descriptive commitment title."
    )
    commitment_type: Optional[str] = Field(
        default=None, description="Structure type (e.g., 'Send or Pay', 'Volume')."
    )
    direction: Optional[str] = Field(
        default=None, description="'Inbound' or 'Outbound'."
    )
    amount: Optional[float] = Field(
        default=None, description="Financial monetary target value."
    )
    capture_rate_pct: Optional[float] = Field(default=None)
    party_from: Optional[str] = Field(
        default=None, description="Committed party paying/sending."
    )
    party_to: Optional[str] = Field(default=None, description="Receiving party.")
    source_type: Optional[str] = Field(default=None)
    conflict_flag: Optional[bool] = Field(default=None)
    conflict_note: Optional[str] = Field(default=None)
    agmt_id: Optional[str] = Field(default=None, description="Associated agreement ID.")


class IOTAgreement(BaseModel):
    """Master container encapsulating all extracted agreement data."""

    header: Optional[AgmtHeaderStg] = Field(
        default_factory=AgmtHeaderStg,
        description="Header attributes and metadata governing the agreement.",
    )
    model: Optional[List[AgmtModelsStg]] = Field(
        default_factory=list,
        description="High-level pricing model structure definitions.",
    )
    normal_model: Optional[List[AgmtMdlNormalStg]] = Field(
        default_factory=list, description="Detailed service rate rules."
    )
    commitment: Optional[List[AgmtCommitment]] = Field(
        default_factory=list, description="Financial or volume commitment obligations."
    )
