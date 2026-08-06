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
        description="Unique agreement identification number or letter reference (e.g., 'IOT Discount Letter Number 5').",
    )

    sender: Optional[str] = Field(
        default=None,
        description="Originating party or group entity executing or managing the agreement (e.g., 'Emirates Telecommunications Group Company PJSC').",
    )

    rp: Optional[str] = Field(
        default=None,
        description="Receiving party, affiliate, or roaming partner entity subject to the agreement (e.g., 'Etisalat Misr', 'Orange EU Affiliates').",
    )

    tap_direction: Optional[str] = Field(
        default=None,
        description="Direction of roaming traffic covered (e.g., 'Inbound', 'Outbound', or 'Bi-lateral').",
    )

    rev_no: Optional[int] = Field(
        default=None,
        description="Revision, version, or amendment sequence number of the agreement.",
    )

    start_date: Optional[str] = Field(
        default=None,
        description="Effective start date of the agreement or discount period (e.g., '1 January 2025' or '2025-01-01').",
    )

    end_date: Optional[str] = Field(
        default=None,
        description="Termination, expiration, or end date of the agreement (e.g., '31 December 2025').",
    )

    remarks: Optional[str] = Field(
        default=None,
        description="General notes, scope summaries, or governing clauses (e.g., 'Back-to-Back IOT Discount Letter').",
    )

    data_level: Optional[str] = Field(
        default=None,
        description="Data aggregation or processing level applied to agreement terms (e.g., 'TAP', 'Group', 'Operator').",
    )

    invoice_amt_type: Optional[str] = Field(
        default=None,
        description="Calculation approach or category for invoiced amounts (e.g., 'Net', 'Gross', 'Fixed', 'Variable').",
    )

    user_act_id: Optional[str] = Field(
        default=None,
        description="User identifier responsible for agreement entry, creation, or execution.",
    )

    created_date: Optional[str] = Field(
        default=None,
        description="Timestamp or date when the agreement record was created in the system.",
    )

    currency_code: Optional[str] = Field(
        default=None,
        description="ISO currency code used for financial commitments and billing rates (e.g., 'EUR', 'USD').",
    )

    auto_renewal: Optional[bool] = Field(
        default=None,
        description="Boolean flag indicating whether the agreement automatically renews upon expiry.",
    )

    is_group_rp: Optional[bool] = Field(
        default=None,
        description="Indicates whether the receiving party comprises a group of operators/affiliates (e.g., 'Orange EU Affiliates').",
    )

    agmt_status: Optional[str] = Field(
        default=None,
        description="Operational status of the agreement (e.g., 'Active', 'Executed', 'Pending', 'Terminated').",
    )

    total_agmt_month: Optional[int] = Field(
        default=None,
        description="Total duration of the agreement measured in full months (e.g., 12).",
    )

    is_rerating_reqd: Optional[bool] = Field(
        default=None,
        description="Flag specifying whether retroactive rerating of traffic TAP records is required.",
    )

    gprs_rule: Optional[str] = Field(
        default=None,
        description="Charging rule or charging mechanism applied specifically to GPRS/Data traffic.",
    )

    gprs_limit: Optional[float] = Field(
        default=None,
        description="Data/GPRS threshold or volume limit (e.g., in MB or GB) defined in the agreement.",
    )

    baseline_rule: Optional[str] = Field(
        default=None,
        description="Rule or logic used to determine baseline thresholds before applying discounted rates.",
    )

    baseline_base_field: Optional[str] = Field(
        default=None,
        description="Target volume/revenue metric used as the baseline comparison field (e.g., 'MOC Minutes', 'Revenue').",
    )

    baseline_value: Optional[float] = Field(
        default=None,
        description="Numerical target value or threshold for baseline rule evaluation.",
    )

    commit_rule: Optional[str] = Field(
        default=None,
        description="Specific commitment rule applied to traffic or billing (e.g., 'Send or Pay', 'Take or Pay').",
    )

    commit_base_field: Optional[str] = Field(
        default=None,
        description="Target metric field evaluated for commitment compliance (e.g., 'Combined Revenue', 'MOC Minutes').",
    )

    commit_value: Optional[float] = Field(
        default=None,
        description="Total financial commitment or threshold amount (e.g., 250000.0, 90000.0).",
    )

    is_group_client: Optional[bool] = Field(
        default=None,
        description="Indicates whether the client or sending side operates as a group entity.",
    )

    parent_agmt_id: Optional[str] = Field(
        default=None,
        description="Identifier of the master framework or parent agreement (e.g., Framework Agreement reference).",
    )

    regen_required: Optional[bool] = Field(
        default=None,
        description="Flag indicating if billing file regeneration is required for modified terms.",
    )

    is_tap_level_agmt: Optional[bool] = Field(
        default=None,
        description="Indicates if settlement terms are defined per individual TAP file or code.",
    )

    is_partial_client: Optional[bool] = Field(
        default=None,
        description="Flag indicating partial client inclusion or conditional client processing.",
    )

    is_partial_rp: Optional[bool] = Field(
        default=None,
        description="Flag indicating partial receiving party inclusion or conditional partner processing.",
    )

    baseline_level: Optional[str] = Field(
        default=None,
        description="Entity or traffic level where baseline calculation is applied (e.g., 'Group', 'TADIG', 'Country').",
    )

    master_agmt_id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the overarching master or umbrella agreement.",
    )

    modified_user: Optional[str] = Field(
        default=None,
        description="User or process name that last modified the agreement record.",
    )

    modified_date: Optional[str] = Field(
        default=None, description="Date or timestamp when the record was last modified."
    )

    agmt_type: Optional[str] = Field(
        default=None,
        description="Classification category of the agreement (e.g., 'IOT Discount Letter', 'Back-to-Back Agreement').",
    )

    bulk_id: Optional[str] = Field(
        default=None,
        description="Identifier used when processing agreements in bulk ingestion jobs.",
    )

    is_baseline_applicable: Optional[bool] = Field(
        default=None,
        description="Flag indicating whether baseline rules apply before discounting.",
    )

    agmt_level_rc_type: Optional[str] = Field(
        default=None,
        description="Type of recurring charge applied at the global agreement level.",
    )

    spl_remarks: Optional[str] = Field(
        default=None,
        description="Special conditions, exclusions, or exceptions (e.g., 'Excludes premium and satellite calls', 'No call setup charges').",
    )

    currency_agmt: Optional[str] = Field(
        default=None,
        description="Currency used specifically for agreement calculations if different from primary billing currency.",
    )

    imsi_activation_type: Optional[str] = Field(
        default=None,
        description="Activation mechanism or classification for IMSIs covered under the agreement.",
    )

    imsi_activation_criteria: Optional[str] = Field(
        default=None,
        description="Criteria or threshold conditions required for IMSI activation under agreed terms.",
    )

    rap_chrg: Optional[float] = Field(
        default=None,
        description="Returned Account Procedure (RAP) fee rate or total penalty charge.",
    )

    rap_vol: Optional[float] = Field(
        default=None, description="RAP volume threshold or tolerance unit count."
    )

    exchange_rate_type: Optional[str] = Field(
        default=None,
        description="Method or standard used for exchange rate conversions (e.g., 'Fixed', 'ECB Monthly Average').",
    )

    agmt_level_rc_var_type: Optional[str] = Field(
        default=None,
        description="Variable logic classification for agreement-level recurring charges.",
    )

    agmt_doc_status: Optional[str] = Field(
        default=None,
        description="Approval or document workflow status (e.g., 'Draft', 'Executed', 'Signed').",
    )

    agmt_nego_status: Optional[str] = Field(
        default=None,
        description="Current negotiation stage (e.g., 'Finalized', 'Under Review', 'Agreed').",
    )

    inc_in_accrl_rpt: Optional[bool] = Field(
        default=None,
        description="Indicates whether expected revenues/commitments should be included in financial accrual reports.",
    )

    is_m2m_applcbl: Optional[bool] = Field(
        default=None,
        description="Flag specifying whether machine-to-machine (M2M) traffic terms apply.",
    )

    agmt_verified: Optional[bool] = Field(
        default=None,
        description="Boolean flag indicating whether the agreement data has been verified against the physical document.",
    )

    agmt_verified_by: Optional[str] = Field(
        default=None,
        description="Name or ID of the user who performed document verification.",
    )

    agmt_verified_date: Optional[str] = Field(
        default=None, description="Date when document verification was completed."
    )


class AgmtModelsStg(BaseModel):
    """Represents high-level pricing model definitions linked to an agreement (AGMT_MODELS_STG)."""

    model_seq: Optional[int] = Field(
        default=None,
        description="Sequential index or priority order of the pricing model within the agreement.",
    )
    agmt_id: Optional[str] = Field(
        default=None, description="Unique identifier of the parent agreement."
    )
    model_type: Optional[str] = Field(
        default=None,
        description="Type of pricing model applied (e.g., 'Tiered', 'Flat Rate', 'Commitment', 'Incremental').",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Descriptive name of the model structure (e.g., 'Orange EU Outbound Discount Model').",
    )


class AgmtMdlNormalStg(BaseModel):
    """Represents specific service charging structures, rates, and charging intervals (AGMT_MDL_NORMAL_STG)."""

    agmt_id: Optional[str] = Field(
        default=None, description="Unique identifier of the parent agreement."
    )
    model_seq: Optional[int] = Field(
        default=None,
        description="Sequence number mapping this rate definition to its parent model entry.",
    )
    rec_type: Optional[str] = Field(
        default=None,
        description="Service record type being rated (e.g., 'MOC', 'MTC', 'SMS', 'Data').",
    )
    zone_code: Optional[str] = Field(
        default=None,
        description="Target geographic zone or destination group code applied to the rate.",
    )
    rate_currency: Optional[str] = Field(
        default=None,
        description="ISO currency code for the specific rate definition (e.g., 'EUR').",
    )
    pra_rate_type: Optional[str] = Field(
        default=None,
        description="Pay Payable Rate Agreement (PRA) structure type (e.g., 'Linear', 'Incremental', 'Flat').",
    )
    disc_rate_perc: Optional[float] = Field(
        default=None,
        description="Percentage discount applied to standard AA14 IOT rates.",
    )
    charge_include_tax: Optional[bool] = Field(
        default=None,
        description="Indicates whether rates and charges are inclusive of applicable taxes/VAT.",
    )
    charge_field: Optional[str] = Field(
        default=None,
        description="Charging interval or granularity rule (e.g., '1 sec for MOC/MTC', '1KB for Data', 'per SMS').",
    )


class AgmtCommitment(BaseModel):
    """Represents financial or volumetric commitment commitments defined between parties (AGMT_COMMITMENT)."""

    agmt_id: Optional[str] = Field(
        default=None, description="Unique identifier of the associated agreement."
    )
    commitment_name: Optional[str] = Field(
        default=None,
        description="Descriptive name of the commitment obligation (e.g., 'Etisalat Misr Minimum Financial Commitment').",
    )
    commitment_type: Optional[str] = Field(
        default=None,
        description="Structure of the commitment obligation (e.g., 'Send or Pay', 'Take or Pay', 'Fixed Revenue').",
    )
    direction: Optional[str] = Field(
        default=None,
        description="Traffic or cashflow direction for the commitment (e.g., 'Inbound', 'Outbound').",
    )
    amount: Optional[float] = Field(
        default=None,
        description="Financial commitment target value in agreement currency (e.g., 90000.0, 375000.0).",
    )
    capture_rate_pct: Optional[float] = Field(
        default=None,
        description="Percentage cap or capture factor applied toward commitment achievement.",
    )
    party_from: Optional[str] = Field(
        default=None,
        description="Party responsible for fulfilling or paying the commitment (e.g., 'Etisalat Misr', 'Orange EU Affiliates').",
    )
    party_to: Optional[str] = Field(
        default=None,
        description="Receiving party entitled to the commitment payment or traffic (e.g., 'Orange EU Affiliates', 'Etisalat Misr').",
    )


class IOTAgreement(BaseModel):
    """Master container encapsulating header metadata, pricing models, normal rates, and commitments for an IOT agreement."""

    header: Optional[AgmtHeaderStg] = Field(
        default=None,
        description="Header attributes and metadata governing the agreement.",
    )
    model: Optional[AgmtModelsStg] = Field(
        default=None, description="High-level pricing model structure definition."
    )
    normal_model: Optional[AgmtMdlNormalStg] = Field(
        default=None,
        description="Detailed service rate rules, charging increments, and currency specifications.",
    )
    commitment: Optional[AgmtCommitment] = Field(
        default=None,
        description="Financial or volume commitment obligations established between parties.",
    )
