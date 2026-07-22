from typing import List, Optional
from pydantic import BaseModel, Field

class AgmtHeaderStg(BaseModel):
    """Represents the AGMT_HEADER_STG table structure."""
    agmt_id: Optional[str] = Field(default=None, description="Agreement ID")
    sender: Optional[str] = None
    rp: Optional[str] = None
    tap_direction: Optional[str] = None
    rev_no: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    remarks: Optional[str] = None
    data_level: Optional[str] = None
    invoice_amt_type: Optional[str] = None
    user_act_id: Optional[str] = None
    created_date: Optional[str] = None
    currency_code: Optional[str] = None
    auto_renewal: Optional[bool] = None
    is_group_rp: Optional[bool] = None
    agmt_status: Optional[str] = None
    total_agmt_month: Optional[int] = None
    is_rerating_reqd: Optional[bool] = None
    gprs_rule: Optional[str] = None
    gprs_limit: Optional[float] = None
    baseline_rule: Optional[str] = None
    baseline_base_field: Optional[str] = None
    baseline_value: Optional[float] = None
    commit_rule: Optional[str] = None
    commit_base_field: Optional[str] = None
    commit_value: Optional[float] = None
    is_group_client: Optional[bool] = None
    parent_agmt_id: Optional[str] = None
    regen_required: Optional[bool] = None
    is_tap_level_agmt: Optional[bool] = None
    is_partial_client: Optional[bool] = None
    is_partial_rp: Optional[bool] = None
    baseline_level: Optional[str] = None
    master_agmt_id: Optional[str] = None
    modified_user: Optional[str] = None
    modified_date: Optional[str] = None
    agmt_type: Optional[str] = None
    bulk_id: Optional[str] = None
    is_baseline_applicable: Optional[bool] = None
    agmt_level_rc_type: Optional[str] = None
    spl_remarks: Optional[str] = None
    currency_agmt: Optional[str] = None
    imsi_activation_type: Optional[str] = None
    imsi_activation_criteria: Optional[str] = None
    rap_chrg: Optional[float] = None
    rap_vol: Optional[float] = None
    exchange_rate_type: Optional[str] = None
    agmt_level_rc_var_type: Optional[str] = None
    agmt_doc_status: Optional[str] = None
    agmt_nego_status: Optional[str] = None
    inc_in_accrl_rpt: Optional[bool] = None
    is_m2m_applcbl: Optional[bool] = None
    agmt_verified: Optional[bool] = None
    agmt_verified_by: Optional[str] = None
    agmt_verified_date: Optional[str] = None

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
    """A master container class to group related records for a single agreement."""
    header: Optional[AgmtHeaderStg] = None
    models: List[AgmtModelsStg] = Field(default_factory=list)
    normal_models: List[AgmtMdlNormalStg] = Field(default_factory=list)
    commitments: List[AgmtCommitment] = Field(default_factory=list)