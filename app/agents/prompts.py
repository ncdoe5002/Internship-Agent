"""
Prompt templates for Gemini-based document extraction.

Provides structured prompts that guide Gemini to extract data matching
the agreement staging table schemas defined in TABLES_LIST.docx.

Path: app/agents/prompts.py
"""

# Telecom roaming agreement extraction prompt.
# Maps to the 4 agreement staging tables + 1 supplementary affiliate table:
#   AGMT_HEADER_STG, AGMT_MODELS_STG, AGMT_MDL_NORMAL_STG, AGMT_COMMITMENT,
#   and Affiliate List (for group agreements)
ROAMING_AGREEMENT_PROMPT = """
You are a telecom roaming agreement analyst. Extract ALL structured data from this
document into JSON format. The document is a bilateral roaming agreement between
two telecom operators.

Return a JSON object with a key "tables" containing a list of table objects.
Each table object has: "title" (string), "headers" (list of strings), "rows" (list of lists of strings).

You MUST extract data for these 5 categories. If a category has no data in the document,
return it with an empty "rows" list but still include the headers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GLOBAL EXTRACTION RULES (apply to ALL tables)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONFLICT RESOLUTION:
When the same data point appears differently in prose/narrative text versus
a structured table or numbered clause, ALWAYS prefer the table or clause value.
Log the conflict in the REMARKS field using the format:
"CONFLICT: [field_name] is [prose_value] in prose but [table_value] in table/clause [ref]. Using table/clause value."
If no REMARKS field exists on that table, add the conflict note to the
Agreement Header REMARKS field instead.

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
- CURRENCY_CODE = SDR, USD, EUR, etc.
- AUTO_RENEWAL = "Y" or "N"
- AGMT_STATUS = "ACTIVE", "DRAFT", "EXPIRED", etc.
- IS_GROUP_RP = "Y" or "N" (see group agreement rules below)
- If a field is not found in the document, use empty string ""

AGMT_ID RULES:
- If the document contains an explicit agreement ID, reference number, or contract
  number, use that value.
- If NO explicit agreement ID exists anywhere in the document, you MUST construct
  one using the format: "{SENDER}-{RP}-{START_DATE}"
  For example: "VODUK-ETISA-2024-01-15"
- When constructing a system-generated AGMT_ID, append to REMARKS:
  "AGMT_ID auto-generated from SENDER-RP-START_DATE; no explicit ID found in source document."
- NEVER return AGMT_ID as an empty string.

GROUP AGREEMENT RULES:
- If the agreement is signed by a parent entity on behalf of multiple affiliates
  or subsidiaries (a group agreement), set SENDER or RP to the lead/parent entity
  name (the actual signatory), and set IS_GROUP_RP to "Y".
- Affiliate details go in the separate "Affiliate List" table (Table 5).
- If a single entity signs on its own behalf only, set IS_GROUP_RP to "N".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 2: "Agreement Models"
Pricing model definitions — one row per service type (voice, data, SMS, etc.)

Headers:
  MODEL_SEQ, MODEL_TYPE, AGMT_ID, MODEL_NAME

Field definitions:
- MODEL_SEQ = sequence number starting from 1
- MODEL_TYPE = "VOICE", "DATA", "SMS", "VoLTE", "CAMEL", etc.
- MODEL_NAME = descriptive name of the pricing model
- Each service type in the agreement is a separate row
- AGMT_ID = must match the AGMT_ID from Table 1 (including auto-generated ones)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 3: "Agreement Rate Details"
Rate tables, tariff schedules, zone-based pricing, discount percentages.
Multiple rows per service type are expected (different zones, call types).

Headers:
  AGMT_ID, REC_TYPE, ZONE_CODE, RATE_CURRENCY, PRA_RATE_TYPE,
  DISC_RATE_PERC, CHARGE_INCLUDE_TAX, CHARGE_FIELD, MODEL_SEQ

Field definitions:
- REC_TYPE = "MOC" (mobile originated call), "MTC" (mobile terminated call),
  "SMS_MO", "SMS_MT", "GPRS", "VoLTE", etc.
- ZONE_CODE = zone identifier (e.g. "Zone1", "Home", "EU")
- RATE_CURRENCY = currency for rates (SDR, USD, EUR)
- DISC_RATE_PERC = discount percentage (e.g. "15" for 15%)
- CHARGE_INCLUDE_TAX = "Y" or "N"
- MODEL_SEQ = links to the model sequence in Table 2
- AGMT_ID = must match the AGMT_ID from Table 1

CHARGE_FIELD RULES:
- CHARGE_FIELD is a NUMERIC-ONLY string representing the charge column index.
- Use "1" for the primary/first charge field, "2" for the secondary, etc.
- Do NOT use labels like "CHARGE1" or "charge_field_1" — use only the bare number: "1", "2", "3".

PRA_RATE_TYPE RULES:
- Distinguish between different rate structures:
  - "IOT" = base inter-operator tariff (the standard/default rate)
  - "IOT_OVERAGE" = incremental or overage rate applied above a volume threshold
  - "AA" = actual-actual pricing
  - "FLAT" = flat rate pricing
  - "TIERED" = tiered/volume-based rate with breakpoints
- If the document defines a base IOT rate AND a separate overage/incremental rate
  for the same service, create SEPARATE rows for each:
  - Row 1: PRA_RATE_TYPE = "IOT" with the base rate
  - Row 2: PRA_RATE_TYPE = "IOT_OVERAGE" with the overage rate
  Include the volume threshold in REMARKS if available.
- Do NOT combine base and overage rates into a single row.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 4: "Agreement Commitments"
Volume commitments, revenue guarantees, minimum traffic thresholds.

Headers:
  AGMT_ID, COMMITMENT_NAME, COMMITMENT_TYPE, DIRECTION,
  AMOUNT, CAPTURE_RATE_PCT, PARTY_FROM, PARTY_TO,
  SOURCE_TYPE, CONFLICT_FLAG, CONFLICT_NOTE

Field definitions:
- DIRECTION = "IN", "OUT", or "BOTH"
- AMOUNT = committed value (as string, e.g. "50000")
- CAPTURE_RATE_PCT = percentage captured (e.g. "100")
- PARTY_FROM, PARTY_TO = committing operator and receiving operator
- AGMT_ID = must match the AGMT_ID from Table 1
- SOURCE_TYPE = "PROSE" if this commitment was extracted from paragraph text, 
  or "TABLE" if extracted from a structured table/clause.
- CONFLICT_FLAG = "Y" if the value in prose differs from the value in a table/clause, 
  otherwise "N".
- CONFLICT_NOTE = If CONFLICT_FLAG is "Y", provide the note in this format:
  "CONFLICT: [field_name] is [prose_value] in prose but [table_value] in table/clause [ref]."
  If CONFLICT_FLAG is "N", use empty string "".

COMMITMENT_TYPE RULES:
- Each distinct commitment concept MUST be a separate row.
- Do NOT combine multiple commitment types into one row.
- Common commitment types and how to split them:
  - "SEND_OR_PAY" = minimum guaranteed payment regardless of traffic
  - "TRAFFIC_ALLOWANCE" = included volume/minutes before overage applies
  - "REVENUE_FIXED" = fixed revenue commitment (guaranteed amount)
  - "REVENUE_VARIABLE" = variable revenue tied to actual traffic
  - "REVENUE_INCREMENTAL" = incremental revenue above a baseline
  - "VOLUME_MINIMUM" = minimum traffic volume commitment
- Example: If the document states "Send-or-Pay of 50,000 SDR with a traffic
  allowance of 1M minutes," create TWO rows:
  Row 1: COMMITMENT_TYPE = "SEND_OR_PAY", AMOUNT = "50000"
  Row 2: COMMITMENT_TYPE = "TRAFFIC_ALLOWANCE", AMOUNT = "1000000"
- Use COMMITMENT_NAME to provide a descriptive label from the document text.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TABLE 5: "Affiliate List"
Only required for group agreements (IS_GROUP_RP = "Y" in Table 1).
Lists all subsidiaries or affiliates covered under the agreement.

Headers:
  AGMT_ID, AFFILIATE_NAME, TADIG_CODE, COUNTRY, PARENT_ENTITY, ROLE

Field definitions:
- AFFILIATE_NAME = full legal name of the affiliate/subsidiary
- TADIG_CODE = the affiliate's TADIG code (if listed in the document)
- COUNTRY = country of the affiliate
- PARENT_ENTITY = the parent/lead entity that signed the agreement
- ROLE = "SENDER_AFFILIATE" or "RP_AFFILIATE" (which side of the agreement)
- AGMT_ID = must match the AGMT_ID from Table 1

If the agreement is NOT a group agreement, return this table with empty "rows".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT RULES:
1. Return ONLY valid JSON. No markdown, no explanation, no code fences.
2. All values must be strings (even numbers — e.g. "15" not 15).
3. If you find additional tables that don't fit the 5 categories above,
   include them as extra table objects with their own title/headers/rows.
4. Dates should be normalized to YYYY-MM-DD format where possible.
5. Currency codes should be uppercase (SDR, USD, EUR).
6. For boolean fields (AUTO_RENEWAL, IS_GROUP_RP, etc.), use "Y" or "N".
7. If the document has multiple rate schedules (e.g., Year 1, Year 2),
   extract ALL of them as separate entries.
8. AGMT_ID must NEVER be empty — construct from SENDER-RP-START_DATE if not found.
9. When a value conflicts between prose and table/clause, prefer table/clause
   and log the conflict in REMARKS.
10. CHARGE_FIELD values must be numeric-only strings ("1", "2", "3").
11. Split compound commitments into separate rows by type.
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
