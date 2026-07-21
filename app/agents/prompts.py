"""
Prompt templates for Gemini-based document extraction.

Provides structured prompts that guide Gemini to extract data matching
the agreement staging table schemas defined in TABLES_LIST.docx.

Path: app/agents/prompts.py
"""


# Telecom roaming agreement extraction prompt.
# Maps to the 4 agreement staging tables:
#   AGMT_HEADER_STG, AGMT_MODELS_STG, AGMT_MDL_NORMAL_STG, AGMT_COMMITMENT
ROAMING_AGREEMENT_PROMPT = """
You are a telecom roaming agreement analyst. Extract ALL structured data from this
document into JSON format. The document is a bilateral roaming agreement between
two telecom operators.

Return a JSON object with a key "tables" containing a list of table objects.
Each table object has: "title" (string), "headers" (list of strings), "rows" (list of lists of strings).

You MUST extract data for these 4 categories. If a category has no data in the document,
return it with an empty "rows" list but still include the headers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 1: "Agreement Header"
Agreement metadata: parties involved, dates, currency, rules.
One row per agreement.

Headers:
  SENDER, RP, TAP_DIRECTION, REV_NO, START_DATE, END_DATE, REMARKS,
  DATA_LEVEL, INVOICE_AMT_TYPE, CURRENCY_CODE, AGMT_ID, AUTO_RENEWAL,
  IS_GROUP_RP, AGMT_STATUS, TOTAL_AGMT_MONTH, IS_RERATING_REQD,
  GPRS_RULE, GPRS_LIMIT, BASELINE_RULE, BASELINE_BASE_FIELD, BASELINE_VALUE,
  COMMIT_RULE, COMMIT_BASE_FIELD, COMMIT_VALUE, AGMT_TYPE,
  IS_BASELINE_APPLICABLE, CURRENCY_AGMT, EXCHANGE_RATE_TYPE

Field definitions:
- SENDER = operator sending/proposing the agreement (TADIG code or operator name)
- RP = roaming partner (the other operator)
- TAP_DIRECTION = "IN" or "OUT" or "BILATERAL"
- START_DATE, END_DATE = agreement validity period (format: YYYY-MM-DD)
- REMARKS = any additional notes or comments
- DATA_LEVEL = "AGREEMENT", "MODEL", "RATE", etc.
- INVOICE_AMT_TYPE = "GROSS", "NET", "BOTH"
- AGMT_ID = unique identifier for the agreement (string) PRIMARY KEY
- CURRENCY_CODE = SDR, USD, EUR, etc.
- AUTO_RENEWAL = "Y" or "N"
- IS_GROUP_RP = "Y" or "N" ?
- AGMT_STATUS = "ACTIVE", "DRAFT", "EXPIRED", etc.
- TOTAL_AGMT_MONTH = total months of the agreement (as string, e.g. "24")
- IS_RERATING_REQD = "Y" or "N" ?
- GPRS_RULE = "APPLICABLE" or "NOT_APPLICABLE" ?
- GPRS_LIMIT = numeric limit for GPRS (as string, e.g. "1000000")
- BASELINE_RULE = "APPLICABLE" or "NOT_APPLICABLE" ? 
- BASELINE_BASE_FIELD = field used for baseline calculation (e.g. "CHARGE1") ?
- BASELINE_VALUE = baseline value (as string, e.g. "50000") 
- COMMIT_RULE = "APPLICABLE" or "NOT_APPLICABLE" ?
- COMMIT_BASE_FIELD = field used for commitment calculation (e.g. "CHARGE2") ?
- COMMIT_VALUE = commitment value (as string, e.g. "100000")
- AGMT_TYPE = "BILATERAL", "MULTILATERAL", "FRAMEWORK", etc.
- IS_BASELINE_APPLICABLE = "Y" or "N" ?
- CURRENCY_AGMT = currency used for the agreement (SDR, USD, EUR)
- EXCHANGE_RATE_TYPE = "FIXED", "FLOATING", "MARKET", etc ?
- If a field is not found in the document, use empty string ""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 2: "Agreement Models"
Pricing model definitions — one row per service type (voice, data, SMS, etc.)

Headers:
  MODEL_SEQ, MODEL_TYPE, AGMT_ID, MODEL_NAME

Field definitions:
- MODEL_SEQ = sequence number starting from 1
- MODEL_TYPE = "VOICE", "DATA", "SMS", "VoLTE", "CAMEL", etc.
- MODEL_NAME = descriptive name of the pricing model
- AGMT_ID = Unique identifier linking to the agreement header (from Table 1)
- Each service type in the agreement is a separate row

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 3: "Agreement Rate Details"
Rate tables, tariff schedules, zone-based pricing, discount percentages.
Multiple rows per service type are expected (different zones, call types).

Headers:
  AGMT_ID, REC_TYPE, ZONE_CODE, RATE_CURRENCY, PRA_RATE_TYPE,
  DISC_RATE_PERC, CHARGE_INCLUDE_TAX, CHARGE_FIELD, MODEL_SEQ

Field definitions:
- AGMT_ID = links to the agreement header in Table 1
- REC_TYPE = "MOC" (mobile originated call), "MTC" (mobile terminated call),
  "SMS_MO", "SMS_MT", "GPRS", "VoLTE", etc.
- ZONE_CODE = zone identifier (e.g. "Zone1", "Home", "EU")
- RATE_CURRENCY = currency for rates (SDR, USD, EUR)
- PRA_RATE_TYPE = "IOT" (inter-operator tariff), "AA" (actual actual), "FLAT", etc.
- DISC_RATE_PERC = discount percentage (e.g. "15" for 15%)
- CHARGE_INCLUDE_TAX = "Y" or "N" indicating if tax is included in the charge
- CHARGE_FIELD = charge field this rate applies to (e.g. "CHARGE1", "CHARGE2") ?
- MODEL_SEQ = links to the model sequence in Table 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 4: "Agreement Commitments"
Volume commitments, revenue guarantees, minimum traffic thresholds.
Not all agreements include these.

Headers:
  AGMT_ID, COMMITMENT_NAME, COMMITMENT_TYPE, DIRECTION,
  AMOUNT, CAPTURE_RATE_PCT, PARTY_FROM, PARTY_TO

Field definitions:
- AGMT_ID = links to the agreement header in Table 1
- COMMITMENT_TYPE = "VOLUME", "REVENUE", "TRAFFIC", "MINUTES", etc.
- DIRECTION = "IN", "OUT", or "BOTH" 
- AMOUNT = committed value (as string, e.g. "50000")
- CAPTURE_RATE_PCT = percentage captured (e.g. "100")
- PARTY_FROM, PARTY_TO = committing operator and receiving operator

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT RULES:
1. Return ONLY valid JSON. No markdown, no explanation, no code fences.
2. All values must be strings (even numbers — e.g. "15" not 15).
3. If you find additional tables that don't fit the 4 categories above,
   include them as extra table objects with their own title/headers/rows.
4. Dates should be normalized to YYYY-MM-DD format where possible.
5. Currency codes should be uppercase (SDR, USD, EUR).
6. For boolean fields (AUTO_RENEWAL, IS_GROUP_RP, etc.), use "Y" or "N".
7. If the document has multiple rate schedules (e.g., Year 1, Year 2),
   extract ALL of them as separate entries.
"""


# Generic fallback prompt for non-roaming documents or unknown formats.
GENERIC_TABLE_EXTRACTION_PROMPT = """
Extract ALL tabular data from this document into JSON format.

Return a JSON object with a key "tables" containing a list of table objects.
Each table object must have:
- "title": string describing what the table contains
- "headers": list of column header strings
- "rows": list of lists of strings (each inner list is one row)

Rules:
1. Return ONLY valid JSON. No markdown, no code fences, no explanation.
2. All cell values must be strings.
3. Extract every table you can find, including rates, schedules, lists, and metadata.
4. If a section has key-value pairs (not a table), convert them to a 2-column table
   with headers ["Field", "Value"].
5. Preserve the original structure — don't merge or split tables.
"""