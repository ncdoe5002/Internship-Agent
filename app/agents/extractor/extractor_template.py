from typing import List
from datetime import datetime

from typing import List, Optional
from pydantic import BaseModel, Field

class AgmtHeaderStg:
    """Represents the AGMT_HEADER_STG table structure[cite: 2]."""

    def __init__(
        self,
        agmt_id: str,
        sender: str,
        rp: str,
        tap_direction: str,
        rev_no: int,
        start_date: datetime,
        end_date: datetime,
        remarks: str,
        data_level: str,
        invoice_amt_type: str,
        user_act_id: str,
        created_date: datetime,
        currency_code: str,
        auto_renewal: bool,
        is_group_rp: bool,
        agmt_status: str,
        total_agmt_month: int,
        is_rerating_reqd: bool,
        gprs_rule: str,
        gprs_limit: float,
        baseline_rule: str,
        baseline_base_field: str,
        baseline_value: float,
        commit_rule: str,
        commit_base_field: str,
        commit_value: float,
        is_group_client: bool,
        parent_agmt_id: str,
        regen_required: bool,
        is_tap_level_agmt: bool,
        is_partial_client: bool,
        is_partial_rp: bool,
        baseline_level: str,
        master_agmt_id: str,
        modified_user: str,
        modified_date: datetime,
        agmt_type: str,
        bulk_id: str,
        is_baseline_applicable: bool,
        agmt_level_rc_type: str,
        spl_remarks: str,
        currency_agmt: str,
        imsi_activation_type: str,
        imsi_activation_criteria: str,
        rap_chrg: float,
        rap_vol: float,
        exchange_rate_type: str,
        agmt_level_rc_var_type: str,
        agmt_doc_status: str,
        agmt_nego_status: str,
        inc_in_accrl_rpt: bool,
        is_m2m_applcbl: bool,
        agmt_verified: bool,
        agmt_verified_by: str,
        agmt_verified_date: datetime,
    ):
        self.agmt_id = agmt_id
        self.sender = sender
        self.rp = rp
        self.tap_direction = tap_direction
        self.rev_no = rev_no
        self.start_date = start_date
        self.end_date = end_date
        self.remarks = remarks
        self.data_level = data_level
        self.invoice_amt_type = invoice_amt_type
        self.user_act_id = user_act_id
        self.created_date = created_date
        self.currency_code = currency_code
        self.auto_renewal = auto_renewal
        self.is_group_rp = is_group_rp
        self.agmt_status = agmt_status
        self.total_agmt_month = total_agmt_month
        self.is_rerating_reqd = is_rerating_reqd
        self.gprs_rule = gprs_rule
        self.gprs_limit = gprs_limit
        self.baseline_rule = baseline_rule
        self.baseline_base_field = baseline_base_field
        self.baseline_value = baseline_value
        self.commit_rule = commit_rule
        self.commit_base_field = commit_base_field
        self.commit_value = commit_value
        self.is_group_client = is_group_client
        self.parent_agmt_id = parent_agmt_id
        self.regen_required = regen_required
        self.is_tap_level_agmt = is_tap_level_agmt
        self.is_partial_client = is_partial_client
        self.is_partial_rp = is_partial_rp
        self.baseline_level = baseline_level
        self.master_agmt_id = master_agmt_id
        self.modified_user = modified_user
        self.modified_date = modified_date
        self.agmt_type = agmt_type
        self.bulk_id = bulk_id
        self.is_baseline_applicable = is_baseline_applicable
        self.agmt_level_rc_type = agmt_level_rc_type
        self.spl_remarks = spl_remarks
        self.currency_agmt = currency_agmt
        self.imsi_activation_type = imsi_activation_type
        self.imsi_activation_criteria = imsi_activation_criteria
        self.rap_chrg = rap_chrg
        self.rap_vol = rap_vol
        self.exchange_rate_type = exchange_rate_type
        self.agmt_level_rc_var_type = agmt_level_rc_var_type
        self.agmt_doc_status = agmt_doc_status
        self.agmt_nego_status = agmt_nego_status
        self.inc_in_accrl_rpt = inc_in_accrl_rpt
        self.is_m2m_applcbl = is_m2m_applcbl
        self.agmt_verified = agmt_verified
        self.agmt_verified_by = agmt_verified_by
        self.agmt_verified_date = agmt_verified_date


class AgmtModelsStg:
    """Represents the AGMT_MODELS_STG table structure[cite: 2]."""

    def __init__(self, model_seq: int, agmt_id: str, model_type: str, model_name: str):
        self.model_seq = model_seq
        self.agmt_id = agmt_id
        self.model_type = model_type
        self.model_name = model_name
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


class AgmtMdlNormalStg:
    """Represents the AGMT_MDL_NORMAL_STG table structure[cite: 2]."""

    def __init__(
        self,
        agmt_id: str,
        model_seq: int,
        rec_type: str,
        zone_code: str,
        rate_currency: str,
        pra_rate_type: str,
        disc_rate_perc: float,
        charge_include_tax: bool,
        charge_field: str,
    ):
        self.agmt_id = agmt_id
        self.model_seq = model_seq
        self.rec_type = rec_type
        self.zone_code = zone_code
        self.rate_currency = rate_currency
        self.pra_rate_type = pra_rate_type
        self.disc_rate_perc = disc_rate_perc
        self.charge_include_tax = charge_include_tax
        self.charge_field = charge_field


class AgmtCommitment:
    """Represents the AGMT_COMMITMENT table structure[cite: 2]."""

    def __init__(
        self,
        agmt_id: str,
        commitment_name: str,
        commitment_type: str,
        direction: str,
        amount: float,
        capture_rate_pct: float,
        party_from: str,
        party_to: str,
    ):
        self.agmt_id = agmt_id
        self.commitment_name = commitment_name
        self.commitment_type = commitment_type
        self.direction = direction
        self.amount = amount
        self.capture_rate_pct = capture_rate_pct
        self.party_from = party_from
        self.party_to = party_to


class IOTAgreement:
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

    def __init__(
        self,
        header: AgmtHeaderStg,
        models: List[AgmtModelsStg],
        normal_models: List[AgmtMdlNormalStg],
        commitments: List[AgmtCommitment],
    ):
        self.header = header
        self.models = models
        self.normal_models = normal_models
        self.commitments = commitments

    header: Optional[AgmtHeaderStg] = None
    models: List[AgmtModelsStg] = Field(default_factory=list)
    normal_models: List[AgmtMdlNormalStg] = Field(default_factory=list)
    commitments: List[AgmtCommitment] = Field(default_factory=list)