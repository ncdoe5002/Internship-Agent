# Orchestrator.py
"""
Orchestrator for coordinating ExtractionAgent, VerificationAgent, and RiskAgent using LangGraph.

This module implements a LangGraph-based workflow that:
1. Runs ExtractionAgent to extract tariff tables from PDF
2. Runs VerificationAgent and RiskAgent in parallel after extraction (LangGraph automatically parallelizes independent nodes)
3. Combines results into a tabular format for manual review
4. Handles individual agent failures with graceful degradation

Note: Parallel execution is achieved through LangGraph's StateGraph, which automatically executes
independent nodes (verification and risk, both depending only on extraction) in parallel.
"""

import logging
import re, os
import hashlib
from difflib import SequenceMatcher
from typing import Any, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

# Local client and friend's extractor functions
from app.agents.extractor.docling_extractor import get_contents
from app.services.llm_client import chat_complete_json

from .risk_agent import RiskAgent, RiskAgentInput, RiskItem, RiskSummary
from .verification_agent import (
    VerificationAgent,
    VerificationAgentInput,
    VerificationResult,
)

from .risk_agent import ReviewTableRow, RiskSummary, RiskAgentInput

logger = logging.getLogger(__name__)


class OrchestratorInput(BaseModel):
    file_path: str
    filename: str
    partner_name: str
    raw_doc_text: str
    baseline_data: dict | None = None
    pre_extracted: dict | None = None
    use_telecom_prompt: bool = True
    pre_extracted_data: dict | None = None


class ReviewSummary(BaseModel):
    total_categories: int = 0
    matched_count: int = 0
    variance_count: int = 0
    new_count: int = 0
    missing_count: int = 0
    overall_status: str = "PENDING"


class OrchestratorOutput(BaseModel):
    partner_name: str
    filename: str
    document_id: str = Field(description="Stable hash identifier (DOC_XXXXXXXXXXXX)")
    verification: VerificationResult
    risk: RiskSummary

    # Plain flat dictionaries for HTML form passthrough
    header: dict[str, Any] = Field(default_factory=dict)
    models: list[dict[str, Any]] = Field(default_factory=list)
    rates: list[dict[str, Any]] = Field(default_factory=list)
    commitments: list[dict[str, Any]] = Field(default_factory=list)

    # Granular detail breakdown for UI inspection
    field_details: dict[str, Any] = Field(default_factory=dict)
    total_fields: int = Field(default=0)

    comparison_table: list[ReviewTableRow] = Field(default_factory=list)
    summary: ReviewSummary = Field(default_factory=ReviewSummary)
    errors: list[str] = Field(default_factory=list)
    raw_extraction: dict = Field(default_factory=dict)


class OrchestratorState(BaseModel):
    """State passed between nodes in the LangGraph workflow."""

    input: OrchestratorInput | None = None
    extraction_result: dict | None = None
    verification_result: VerificationResult | None = None
    risk_result: RiskSummary | None = None
    extraction_error: str | None = None
    verification_error: str | None = None
    risk_error: str | None = None


class ReviewTableRow(BaseModel):
    """Single row in the review table."""

    category: str
    old_rate: float
    new_rate: float
    delta_pct: float
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    ai_notes: str
    verification_status: str
    approval_status: Literal[
        "PENDING_REVIEW", "APPROVED", "REJECTED", "NEEDS_CHANGES"
    ] = "PENDING_REVIEW"


class ReviewSummary(BaseModel):
    """Summary statistics for the review table."""

    total_rows: int
    changed_rows: int
    flagged_rows: int
    highest_risk: Literal["LOW", "MEDIUM", "HIGH"]
    recommendation: str


class AINote(BaseModel):
    """AI-generated note for one flagged category."""

    category: str
    note: str


class AINotesResult(BaseModel):
    """Structured output for AI note generation."""

    notes: list[AINote]


class OrchestratorOutput(BaseModel):
    """Output schema for the orchestrator with tabular review data."""

    review_table: list[ReviewTableRow]
    summary: ReviewSummary
    extraction_data: dict
    verification_data: dict | None = None
    risk_data: dict | None = None
    errors: dict[str, str] = Field(default_factory=dict)

    @property
    def output(self):
        return self


ai_notes_prompt = ChatPromptTemplate.from_template(
    "Given these flagged tariff rate changes:\n{items}\n\n"
    "For each item, explain in one sentence why it was flagged and what "
    "the risk level means for approval."
)


class Orchestrator:
    """
    Orchestrator that coordinates ExtractionAgent, VerificationAgent, and RiskAgent.

    Uses LangGraph for workflow orchestration with parallel execution of
    VerificationAgent and RiskAgent after ExtractionAgent completes.
    """

    def __init__(self, model: Any):
        """
        Initialize the orchestrator with a LangChain-compatible model.

        Args:
            model: LangChain-compatible model (e.g., ChatGoogleGenerativeAI)
        """
        self.model = model
        self.extraction_agent = ExtractionAgent(model)
        self.verification_agent = VerificationAgent()
        self.risk_agent = RiskAgent()
        self.graph = self._build_graph()
        self.extraction_cache = {}  # Simple in-memory cache

    def _get_file_hash(self, file_path: str) -> str:
        """Generate MD5 hash of file for caching."""
        try:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return hashlib.md5(file_path.encode()).hexdigest()

    def get_cached_extraction(self, file_path: str) -> dict | None:
        """Retrieve cached extraction result if available."""
        file_hash = self._get_file_hash(file_path)
        return self.extraction_cache.get(file_hash)

    def cache_extraction(self, file_path: str, result: dict):
        """Cache extraction result for future use."""
        file_hash = self._get_file_hash(file_path)
        self.extraction_cache[file_hash] = result

    def _adapt_staging_schema(self, raw_extraction: dict) -> dict:
        """
        Adapts friend's relational staging tables output into an array of generic JSON tables.
        This maintains compatibility with VerificationAgent and RiskAgent algorithms.
        """
        if "tables" in raw_extraction:
            return raw_extraction
        title_mapping = {
            "header": "AGMT_HEADER_STG",
            "model": "AGMT_MODELS_STG",
            "normal_model": "AGMT_MDL_NORMAL_STG",
            "commitment": "AGMT_COMMITMENT",
        }

        adapted_tables = []
        for table_name, content in raw_extraction.items():
            mapped_title = title_mapping.get(table_name, table_name)

            if isinstance(content, list) and len(content) > 0:
                first_row = content[0]
                if isinstance(first_row, dict):
                    headers = list(first_row.keys())
                    rows = []
                    for row in content:
                        if hasattr(row, "model_dump"):
                            row = row.model_dump()
                        rows.append(
                            [
                                str(row.get(h, "")) if row.get(h) is not None else ""
                                for h in headers
                            ]
                        )

                    # Deduplicate AGMT_ID entries for header table
                    if mapped_title == "AGMT_HEADER_STG":
                        rows = self._deduplicate_header_rows(headers, rows)

                    adapted_tables.append(
                        {"title": mapped_title, "headers": headers, "rows": rows}
                    )
            elif isinstance(content, dict) and content:
                headers = list(content.keys())
                rows = [
                    [
                        str(content.get(h, "")) if content.get(h) is not None else ""
                        for h in headers
                    ]
                ]
                adapted_tables.append(
                    {"title": mapped_title, "headers": headers, "rows": rows}
                )

        return {"tables": adapted_tables}

    def _deduplicate_header_rows(
        self, headers: list[str], rows: list[list[str]]
    ) -> list[list[str]]:
        """Remove duplicate AGMT_ID entries and merge conflicting data intelligently."""
        if not headers or not rows:
            return rows

        try:
            agmt_id_idx = headers.index("AGMT_ID")
        except ValueError:
            return rows  # No AGMT_ID column, no deduplication needed

        seen_agmt_ids = {}
        deduplicated_rows = []

        for row in rows:
            if len(row) <= agmt_id_idx:
                continue  # Skip malformed rows

            agmt_id = row[agmt_id_idx]
            if not agmt_id or agmt_id == "":
                continue  # Skip rows without AGMT_ID

            if agmt_id not in seen_agmt_ids:
                seen_agmt_ids[agmt_id] = row
                deduplicated_rows.append(row)
            else:
                # Merge conflicting data intelligently
                existing_row = seen_agmt_ids[agmt_id]
                merged_row = self._merge_header_rows(headers, existing_row, row)
                seen_agmt_ids[agmt_id] = merged_row
                # Replace the existing row with merged version
                deduplicated_rows = [
                    merged_row if r == existing_row else r for r in deduplicated_rows
                ]

        return deduplicated_rows

    def _merge_header_rows(
        self, headers: list[str], row1: list[str], row2: list[str]
    ) -> list[str]:
        """Merge two header rows intelligently, preferring non-null values."""
        merged = []
        for i, header in enumerate(headers):
            val1 = row1[i] if i < len(row1) else ""
            val2 = row2[i] if i < len(row2) else ""

            # Prefer non-null/non-empty values
            if val1 and val1 not in ("", "null", "None"):
                merged.append(val1)
            elif val2 and val2 not in ("", "null", "None"):
                merged.append(val2)
            else:
                merged.append(val1 if val1 else val2)

        return merged

    def select_relevant_context(self, doc_text: str, target_fields: list[str]) -> str:
        """Extract only relevant sections based on target fields for efficient LLM processing."""
        if not target_fields:
            return doc_text[:5000]  # Default truncation

        sections = {
            "header": [
                "parties",
                "effective date",
                "currency",
                "agreement",
                "sender",
                "receiving party",
                "rp",
            ],
            "rates": [
                "rate",
                "charge",
                "per minute",
                "per sms",
                "per mb",
                "price",
                "cost",
                "tariff",
            ],
            "commitment": [
                "commitment",
                "allowance",
                "volume",
                "send or pay",
                "revenue",
                "amount",
            ],
        }

        relevant_keywords = []
        for field in target_fields:
            field_lower = str(field).lower()
            if any(
                kw in field_lower
                for kw in ["header", "sender", "rp", "date", "currency", "agmt_id"]
            ):
                relevant_keywords.extend(sections["header"])
            elif any(
                kw in field_lower for kw in ["rate", "model", "charge", "price", "cost"]
            ):
                relevant_keywords.extend(sections["rates"])
            elif any(
                kw in field_lower for kw in ["commit", "allowance", "volume", "revenue"]
            ):
                relevant_keywords.extend(sections["commitment"])

        # Extract sentences containing relevant keywords
        sentences = re.split(r"(?<=[.!?])\s+", doc_text)
        relevant_sentences = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(kw in sentence_lower for kw in relevant_keywords):
                relevant_sentences.append(sentence)

        # If no relevant sentences found, return first 3000 chars as fallback
        if not relevant_sentences:
            return doc_text[:3000]

        # Return up to 50 relevant sentences, limit to 4000 chars
        selected_text = ". ".join(relevant_sentences[:50])
        return selected_text[:4000] if len(selected_text) > 4000 else selected_text

    # --- Utility Methods for Downstream Risk & Comparison ---

    def _normalize_category(self, cat: str) -> str:
        s = cat.strip().lower()
        s = re.sub(r"[\/\_\-\s]+", " ", s)
        return s.strip()

    def _fuzzy_match_category(
        self, extracted: str, baseline_categories: list[str], threshold: float = 0.8
    ) -> tuple[str | None, float]:
        """
        Fuzzy match extracted category against baseline categories using token overlap.

        Args:
            extracted: Normalized extracted category
            baseline_categories: List of normalized baseline categories
            threshold: Minimum similarity score (0-1) to consider a match

        Returns:
            Tuple of (matched_baseline_category, similarity_score) or (None, 0) if no match
        """
        best_match = None
        best_score = 0.0

        for baseline_cat in baseline_categories:
            # Use SequenceMatcher for similarity
            similarity = SequenceMatcher(None, extracted, baseline_cat).ratio()

            # Also check token overlap for better matching on phrases
            extracted_tokens = set(extracted.split())
            baseline_tokens = set(baseline_cat.split())

            if extracted_tokens and baseline_tokens:
                token_overlap = len(extracted_tokens & baseline_tokens) / len(
                    extracted_tokens | baseline_tokens
                )
                similarity = max(similarity, token_overlap)

            if similarity > best_score:
                best_score = similarity
                best_match = baseline_cat

        if best_score >= threshold:
            return best_match, best_score
        return None, best_score

    def _parse_rate(self, rate_str: str) -> float | None:
        """
        Parse rate string to float, handling currency symbols, separators, and special values.

        Args:
            rate_str: Raw rate string from table cell

        Returns:
            Parsed float value, or None if the value is N/A/blank/unparseable
        """
        if not rate_str:
            return None

        rate_str = str(rate_str).strip()

        # Handle N/A, NA, blank, etc.
        if rate_str.upper() in ["N/A", "NA", "NOT APPLICABLE", "-", ""]:
            return None
        s = re.sub(r"[€$£,]", "", s)
        match = re.search(r"-?\d+(\.\d+)?", s)
        return float(match.group(0)) if match else None

    def _find_column_indices(self, headers: list[str]) -> tuple[int, int]:
        cat_idx = 0
        rate_idx = 1
        for idx, h in enumerate(headers):
            h_upper = str(h).upper().strip()
            if any(
                k in h_upper
                for k in ["DESTINATION", "CATEGORY", "SERVICE", "ITEM", "ZONE"]
            ):
                cat_idx = idx
            elif any(
                k in h_upper
                for k in ["RATE", "PRICE", "AMOUNT", "COST", "CHARGE", "VALUE"]
            ):
                rate_idx = idx
        return cat_idx, rate_idx

    def _extract_comparison_rows(
        self,
        extracted_tables: dict | None,
        baseline_data: dict | None,
        field_details: dict | None = None,
    ) -> list[ReviewTableRow]:
        rows: list[ReviewTableRow] = []
        extracted_map: dict[str, tuple[float | None, float]] = {}

        # Build rate confidence lookup map if field_details are available
        rate_confidences: dict[str, float] = {}
        if field_details and "rates" in field_details:
            for rate_item in field_details.get("rates", []):
                # Look up rate score from field details
                for k, v in rate_item.items():
                    if hasattr(v, "confidence_score"):
                        rate_confidences[k] = v.confidence_score

        if extracted_tables and "tables" in extracted_tables:
            for table in extracted_tables["tables"]:
                headers = table.get("headers", [])
                table_rows = table.get("rows", [])
                if not headers or not table_rows:
                    continue

                cat_idx, rate_idx = self._find_column_indices(headers)
                for row in table_rows:
                    if len(row) > cat_idx and len(row) > rate_idx:
                        cat_str = str(row[cat_idx]).strip()
                        rate_val = self._parse_rate(row[rate_idx])
                        conf_val = rate_confidences.get(headers[rate_idx], 1.0)
                        if cat_str:
                            extracted_map[cat_str] = (rate_val, conf_val)

        baseline_map: dict[str, float | None] = {}
        if baseline_data and "tables" in baseline_data:
            for table in baseline_data["tables"]:
                headers = table.get("headers", [])
                table_rows = table.get("rows", [])
                if not headers or not table_rows:
                    continue

                cat_idx, rate_idx = self._find_column_indices(headers)
                for row in table_rows:
                    if len(row) > cat_idx and len(row) > rate_idx:
                        cat_str = str(row[cat_idx]).strip()
                        rate_val = self._parse_rate(row[rate_idx])
                        if cat_str:
                            baseline_map[cat_str] = rate_val

        matched_baseline_keys = set()

        for ext_cat, (ext_rate, ext_conf) in extracted_map.items():
            match_key = self._fuzzy_match_category(ext_cat, list(baseline_map.keys()))

            if match_key:
                matched_baseline_keys.add(match_key)
                base_rate = baseline_map[match_key]

                if ext_rate is not None and base_rate is not None and base_rate != 0:
                    pct = round(((ext_rate - base_rate) / base_rate) * 100, 2)
                else:
                    pct = None

                status = (
                    "MATCH"
                    if ext_rate is not None
                    and base_rate is not None
                    and abs(ext_rate - base_rate) < 1e-4
                    else "VARIANCE"
                )
                flag = "LOW"
                if status == "VARIANCE" and pct is not None:
                    if abs(pct) > self.risk_agent.config.high_variance_threshold:
                        flag = "HIGH"
                    elif abs(pct) > self.risk_agent.config.moderate_variance_threshold:
                        flag = "MEDIUM"

                rows.append(
                    ReviewTableRow(
                        category=ext_cat,
                        proposed_rate=ext_rate,
                        baseline_rate=base_rate,
                        pct_change=pct,
                        status=status,
                        flag=flag,
                        confidence_score=ext_conf,
                    )
                )
            else:
                rows.append(
                    ReviewTableRow(
                        category=ext_cat,
                        proposed_rate=ext_rate,
                        baseline_rate=None,
                        pct_change=None,
                        status="NEW",
                        flag="LOW",
                        confidence_score=ext_conf,
                    )
                )

        for base_cat, base_rate in baseline_map.items():
            if base_cat not in matched_baseline_keys:
                rows.append(
                    ReviewTableRow(
                        category=base_cat,
                        proposed_rate=None,
                        baseline_rate=base_rate,
                        pct_change=None,
                        status="MISSING",
                        flag="MEDIUM",
                        confidence_score=1.0,
                    )
                )

        return rows

    # --- Graph Execution Nodes ---

    def _extraction_node(self, state: OrchestratorState) -> dict:
        if state.input is None:
            return {"extraction_result": None, "extraction_error": "No input provided"}
        try:
            # Check cache first
            cached_result = self.get_cached_extraction(state.input.file_path)
            if cached_result:
                logger.info(f"Using cached extraction for {state.input.file_path}")
                return {"extraction_result": cached_result, "extraction_error": None}

            pre_extracted = state.input.pre_extracted or state.input.pre_extracted_data
            if pre_extracted:
                adapted_result = self._adapt_staging_schema(pre_extracted)
                self.cache_extraction(state.input.file_path, adapted_result)
                return {"extraction_result": adapted_result, "extraction_error": None}

            # Fallback: run Docling if pre_extracted not provided
            api_key = os.environ.get("GEMINI_API_KEY", "")
            header, model, normal_model, commitment = get_contents(
                filePath=state.input.file_path,
                use_ocr=True,
                api_key=api_key,
            )

            def _normalize_item(item: Any) -> dict:
                if hasattr(item, "model_dump"):
                    return item.model_dump()
                if isinstance(item, dict):
                    return item
                if isinstance(item, tuple) and len(item) == 2:
                    key, value = item
                    return {str(key): value}
                return {"value": item}

            raw_extracted = {
                "header": header.model_dump() if header else {},
                "model": [_normalize_item(m) for m in model] if model else [],
                "normal_model": (
                    [_normalize_item(nm) for nm in normal_model] if normal_model else []
                ),
                "commitment": (
                    [_normalize_item(c) for c in commitment] if commitment else []
                ),
            }
            adapted_result = self._adapt_staging_schema(raw_extracted)
            self.cache_extraction(state.input.file_path, adapted_result)
            return {"extraction_result": adapted_result, "extraction_error": None}
        except Exception as e:
            logger.error(f"Extraction failed for {state.input.filename}: {str(e)}")
            return {"extraction_result": None, "extraction_error": str(e)}

    def _verification_node(self, state: OrchestratorState) -> dict:
        """
        Run VerificationAgent to verify extracted data.

        Args:
            state: Current orchestrator state

        Returns:
            Updated state with verification result or error
        """
        if state.input is None:
            return {"risk_result": None, "risk_error": "Input payload missing"}
        try:
            if state.extraction_result is None:
                logger.warning("Skipping verification: extraction failed")
                return {
                    "verification_result": None,
                    "verification_error": "Skipped due to extraction failure",
                }

            # Use intelligent context selection for efficient processing
            relevant_context = self.select_relevant_context(
                state.input.raw_doc_text,
                ["header", "rates", "commitment"],  # Target field categories
            )

            payload = VerificationAgentInput(
                partner_name=state.input.partner_name,
                extracted_tables=state.extraction_result,
                raw_doc_text=relevant_context,  # Use optimized context
                baseline_tables=state.input.baseline_data,
            )
            result = self.verification_agent.run(payload)
            return {"verification_result": result, "verification_error": None}
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            return {"verification_result": None, "verification_error": str(e)}

    def _run_verification_and_risk_parallel(self, state: OrchestratorState) -> dict:
        """Run verification and risk assessment in parallel for improved performance."""
        if state.input is None or state.extraction_result is None:
            return {
                "verification_result": None,
                "verification_error": "Input or extraction missing",
                "risk_result": None,
                "risk_error": "Input or extraction missing",
            }

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit verification task
                verification_future = executor.submit(
                    self._run_verification_task, state
                )

                # Submit risk task (will wait for verification result internally)
                risk_future = executor.submit(
                    self._run_risk_task, state, verification_future
                )

                # Get results
                verification_result = verification_future.result()
                risk_result = risk_future.result()

                return {
                    "verification_result": verification_result["verification_result"],
                    "verification_error": verification_result["verification_error"],
                    "risk_result": risk_result["risk_result"],
                    "risk_error": risk_result["risk_error"],
                }
        except Exception as e:
            logger.error(f"Parallel verification and risk failed: {str(e)}")
            return {
                "verification_result": None,
                "verification_error": str(e),
                "risk_result": None,
                "risk_error": str(e),
            }

    def _run_verification_task(self, state: OrchestratorState) -> dict:
        """Helper method for parallel verification execution."""
        try:
            if state.input is None or state.extraction_result is None:
                return {
                    "verification_result": None,
                    "verification_error": "Input or extraction missing for verification",
                }

            # Use intelligent context selection for efficient processing
            relevant_context = self.select_relevant_context(
                state.input.raw_doc_text,
                ["header", "rates", "commitment"],  # Target field categories
            )

            payload = VerificationAgentInput(
                partner_name=state.input.partner_name,
                extracted_tables=state.extraction_result,
                raw_doc_text=relevant_context,  # Use optimized context
                baseline_tables=state.input.baseline_data,
            )

            result = self.verification_agent.run(payload)

            logger.info(f"Verification completed for {state.input.partner_name}")

            return {"verification_result": result, "verification_error": None}
        except Exception as e:
            logger.error(
                f"Verification failed for {state.input.partner_name}: {str(e)}"
            )
            return {"verification_result": None, "verification_error": str(e)}

    def _run_risk_task(self, state: OrchestratorState, verification_future) -> dict:
        """Helper method for parallel risk execution."""
        try:
            if state.input is None or state.extraction_result is None:
                return {
                    "risk_result": None,
                    "risk_error": "Input or extraction missing for risk evaluation",
                }

            # Wait for verification result
            verification_result = verification_future.result()
            if verification_result["verification_error"]:
                return {
                    "risk_result": None,
                    "risk_error": f"Verification failed: {verification_result['verification_error']}",
                }

            field_details = verification_result["verification_result"].field_details
            comparison_rows = self._extract_comparison_rows(
                state.extraction_result,
                state.input.baseline_data,
                field_details=field_details,
            )

            risk_input = RiskAgentInput(
                partner_name=state.input.partner_name,
                confidence=verification_result["verification_result"].confidence,
                comparison_rows=comparison_rows,
            )

            result = self.risk_agent.assess(risk_input)
            return {"risk_result": result, "risk_error": None}
        except Exception as e:
            logger.error(f"Risk assessment failed: {str(e)}")
            return {"risk_result": None, "risk_error": str(e)}

    def _risk_node(self, state: OrchestratorState) -> dict:
        if state.input is None or state.verification_result is None:
            return {
                "risk_result": None,
                "risk_error": "Input or verification missing for risk evaluation",
            }

        try:
            field_details = state.verification_result.field_details
            comparison_rows = self._extract_comparison_rows(
                state.extraction_result,
                state.input.baseline_data,
                field_details=field_details,
            )

            risk_input = RiskAgentInput(
                partner_name=state.input.partner_name,
                confidence=state.verification_result.confidence,
                comparison_rows=comparison_rows,
            )

            result = self.risk_agent.assess(risk_input)
            return {"risk_result": result, "risk_error": None}
        except Exception as e:
            logger.error(
                f"Risk assessment failed for {state.input.partner_name}: {str(e)}"
            )
            return {"risk_result": None, "risk_error": str(e)}

    def _ai_notes_node(self, state: OrchestratorState) -> dict:
        """Generate AI notes for non-LOW risk items and preserve template notes on failure.

        This node runs after risk assessment and before result combination. It skips
        model invocation when no risk result exists or when all rows are LOW risk.

        Args:
            state: Current orchestrator state.

        Returns:
            dict: Partial state update containing the (possibly annotated) risk result.
        """
        if (
            not state.risk_result
            or not state.risk_result.items
            or self.structured_model is None
        ):
            return {"risk_result": state.risk_result}

        flagged = [i for i in state.risk_result.items if i.risk_level != "LOW"]
        if not flagged:
            return {"risk_result": state.risk_result}

        items_json = [i.model_dump() for i in flagged]
        prompt = (
            f"Given these flagged tariff rate changes:\n{items_json}\n\n"
            f"For each item, explain in one sentence why it was flagged and what the risk level means for approval."
        )
        system_prompt = (
            "Return ONLY a JSON object containing a 'notes' array. "
            "Each object in the array must have a 'category' string and a 'note' string."
        )

        try:
            result = chat_complete_json(prompt, system_prompt)
            notes_list = result.get("notes", []) if isinstance(result, dict) else result
            notes_by_category = {
                n.get("category"): n.get("note")
                for n in notes_list
                if n.get("category")
            }

            for item in state.risk_result.items:
                if item.category in notes_by_category:
                    item.note = notes_by_category[item.category]
        except Exception as e:
            logger.warning(f"AI notes generation failed: {e}. Keeping template notes.")

        return {"risk_result": state.risk_result}

    def _extract_comparison_rows(
        self, extraction_result: dict, baseline_data: dict | None
    ) -> list[RiskItem]:
        """
        Convert extraction result to RiskItem comparison rows.

        Uses header-based column matching, fuzzy category matching, and robust rate parsing.

        Args:
            extraction_result: Extraction result from ExtractionAgent
            baseline_data: Baseline tariff data for comparison

        Returns:
            List of RiskItem objects for risk assessment
        """
        comparison_rows = []

        # Extract tables from extraction result
        tables = extraction_result.get("tables", [])

        # Build baseline category lookup if baseline data exists
        baseline_lookup = {}
        if baseline_data:
            for baseline_table in baseline_data.get("tables", []):
                baseline_headers = baseline_table.get("headers", [])
                baseline_rows = baseline_table.get("rows", [])

                if not isinstance(baseline_headers, list) or not isinstance(
                    baseline_rows, list
                ):
                    logger.warning("Skipping malformed baseline table")
                    continue

                # Find column indices in baseline
                baseline_cat_idx, baseline_rate_idx = self._find_column_indices(
                    baseline_headers
                )

                if baseline_cat_idx is not None and baseline_rate_idx is not None:
                    for baseline_row in baseline_rows:
                        if len(baseline_row) > max(baseline_cat_idx, baseline_rate_idx):
                            category = baseline_row[baseline_cat_idx]
                            rate_str = baseline_row[baseline_rate_idx]
                            normalized_cat = self._normalize_category(category)
                            parsed_rate = self._parse_rate(rate_str)

                            if normalized_cat and parsed_rate is not None:
                                baseline_lookup[normalized_cat] = {
                                    "original": category,
                                    "rate": parsed_rate,
                                }
        is_first_upload = not bool(baseline_data and baseline_data.get("tables"))

        # Process extracted tables
        for table_idx, table in enumerate(tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            if not isinstance(headers, list) or not isinstance(rows, list):
                logger.warning(
                    f"Table {table_idx}: malformed headers or rows, skipping"
                )
                continue

            # Find column indices in extracted table
            category_idx, rate_idx = self._find_column_indices(headers)

            if category_idx is None or rate_idx is None:
                logger.warning(
                    f"Table {table_idx}: Could not identify category/rate columns, skipping"
                )
                continue

            # Get list of normalized baseline categories for fuzzy matching
            baseline_categories = list(baseline_lookup.keys())

            for row_idx, row in enumerate(rows):
                try:
                    # Extract category and rate using identified column indices
                    if len(row) <= max(category_idx, rate_idx):
                        logger.warning(
                            f"Table {table_idx}, row {row_idx}: Row too short, skipping"
                        )
                        continue

                    category = row[category_idx]
                    rate_str = row[rate_idx]

                    if not category:
                        logger.warning(
                            f"Table {table_idx}, row {row_idx}: Empty category, skipping"
                        )
                        continue

                    # Parse new rate
                    new_rate = self._parse_rate(rate_str)
                    if new_rate is None:
                        logger.warning(
                            f"Table {table_idx}, row {row_idx}: Could not parse rate '{rate_str}', skipping"
                        )
                        continue

                    # Match against baseline using normalization and fuzzy matching
                    normalized_category = self._normalize_category(category)
                    old_rate = 0.0
                    match_method = ""

                    # Try exact normalized match first
                    if normalized_category in baseline_lookup:
                        old_rate = baseline_lookup[normalized_category]["rate"]
                        match_method = "exact_normalized"
                    else:
                        # Try fuzzy match
                        matched_baseline, similarity = self._fuzzy_match_category(
                            normalized_category, baseline_categories
                        )
                        if matched_baseline:
                            old_rate = baseline_lookup[matched_baseline]["rate"]
                            match_method = f"fuzzy_match_{similarity:.2f}"
                            logger.info(
                                f"Fuzzy match: '{category}' matched to '{baseline_lookup[matched_baseline]['original']}' "
                                f"with similarity {similarity:.2f}"
                            )
                        else:
                            # No match found - mark as new category
                            match_method = "NEW_CATEGORY"
                            logger.warning(
                                f"Unmatched category: '{category}' (normalized: '{normalized_category}')"
                            )

                    # Calculate delta percentage
                    delta_pct = 0.0
                    if old_rate > 0:
                        delta_pct = ((new_rate - old_rate) / old_rate) * 100

                    # Determine risk level based on delta
                    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
                    if abs(delta_pct) > 50:
                        risk_level = "HIGH"
                    elif abs(delta_pct) > 20:
                        risk_level = "MEDIUM"

                    # Build note with match method and delta info
                    note_parts = []
                    if match_method == "NEW_CATEGORY":
                        note_parts.append("NEW_CATEGORY")
                    elif match_method.startswith("fuzzy_match"):
                        note_parts.append(f"Fuzzy matched ({match_method})")

                    if delta_pct > 0:
                        note_parts.append(f"Rate increased by {delta_pct:.1f}%")
                    elif delta_pct < 0:
                        note_parts.append(f"Rate decreased by {abs(delta_pct):.1f}%")
                    else:
                        note_parts.append("No change")

                    note = "; ".join(note_parts)

                    comparison_rows.append(
                        RiskItem(
                            category=category,
                            old_rate=old_rate,
                            new_rate=new_rate,
                            delta_pct=delta_pct,
                            risk_level=risk_level,
                            note=note,
                        )
                    )

                except Exception as e:
                    logger.error(
                        f"Table {table_idx}, row {row_idx}: Error processing row: {str(e)}"
                    )
                    continue

        return comparison_rows

    def _combine_results_node(self, state: OrchestratorState) -> dict:
        """
        Combine all agent results into tabular format for manual review.

        Args:
            state: Current orchestrator state

        Returns:
            OrchestratorOutput with review table and summary
        """
        logger.info("Combining results for manual review")

        # Build review table from risk results
        review_table = []

        if state.risk_result and state.risk_result.items:
            for item in state.risk_result.items:
                # Determine verification status
                if state.verification_result:
                    verification_status = state.verification_result.status
                elif state.verification_error:
                    verification_status = "VERIFICATION_FAILED"
                else:
                    verification_status = "VERIFICATION_FAILED"

                # Block auto-approvable state if any errors occurred
                if (
                    state.extraction_error
                    or state.verification_error
                    or state.risk_error
                ):
                    verification_status = "ERROR_REQUIRES_REVIEW"

                review_table.append(
                    ReviewTableRow(
                        category=item.category,
                        old_rate=item.old_rate,
                        new_rate=item.new_rate,
                        delta_pct=item.delta_pct,
                        risk_level=item.risk_level,
                        ai_notes=item.note,
                        verification_status=verification_status,
                        approval_status="PENDING_REVIEW",
                    )
                )

        # Build summary
        if state.risk_result:
            recommendation = state.risk_result.recommendation
            if not state.input.baseline_data:
                recommendation = "INITIAL_UPLOAD: Baseline file established for new company. Review tariff tables before committing to database."

            summary = ReviewSummary(
                total_rows=state.risk_result.total_rows,
                changed_rows=state.risk_result.changed_rows,
                flagged_rows=state.risk_result.flagged_rows,
                highest_risk=state.risk_result.highest_risk,
                recommendation=recommendation,
            )

        # Collect errors
        errors = {}
        if state.extraction_error:
            errors["extraction"] = state.extraction_error
        if state.verification_error:
            errors["verification"] = state.verification_error
        if state.risk_error:
            errors.append(f"Risk Error: {state.risk_error}")

        verification = state.verification_result or VerificationResult(
            status="FAILED",
            confidence=0,
            checks=[],
            issues=["Verification stage failed"],
            field_details={},
        )

        risk = state.risk_result or RiskSummary(
            partner_name=state.input.partner_name,
            total_rows=0,
            changed_rows=0,
            flagged_rows=0,
            highest_risk="HIGH",
            recommendation="Assessment incomplete due to errors",
            items=[],
        )

        # 1. Deterministic Document ID using SHA256
        import hashlib

        doc_raw_id = f"{state.input.filename}_{state.input.partner_name}"
        document_id = (
            f"DOC_{hashlib.sha256(doc_raw_id.encode()).hexdigest()[:12].upper()}"
        )

        # 2. Extract Plain Flat Schemas
        flat_header: dict[str, Any] = {}
        flat_models: list[dict[str, Any]] = []
        flat_rates: list[dict[str, Any]] = []
        flat_commitments: list[dict[str, Any]] = []

        tables = (state.extraction_result or {}).get("tables", [])
        for t in tables:
            title = str(t.get("title", "")).upper()
            headers = t.get("headers", [])
            rows = t.get("rows", [])

            if "AGMT_HEADER_STG" in title or "HEADER" in title:
                if rows:
                    flat_header = dict(zip(headers, rows[0]))
            elif "AGMT_MODELS_STG" in title or "MODEL" in title:
                flat_models = [dict(zip(headers, r)) for r in rows]
            elif (
                "AGMT_MDL_NORMAL_STG" in title
                or "NORMAL_MODEL" in title
                or "NORMAL" in title
                or "RATE" in title
            ):
                flat_rates = [dict(zip(headers, r)) for r in rows]
            elif "AGMT_COMMITMENT" in title or "COMMITMENT" in title:
                flat_commitments = [dict(zip(headers, r)) for r in rows]

        # 3. Calculate Total Extracted Fields
        total_fields = (
            len(flat_header)
            + sum(len(m) for m in flat_models)
            + sum(len(r) for r in flat_rates)
            + sum(len(c) for c in flat_commitments)
        )

        # 4. Extract DB vs Uploaded Comparison Rows
        comparison_rows = self._extract_comparison_rows(
            state.extraction_result, state.input.baseline_data
        )

        if state.risk_result:
            notes_map = {item.category: item.note for item in state.risk_result.items}
            for row in comparison_rows:
                if row.category in notes_map:
                    row.ai_note = notes_map[row.category]

        summary = ReviewSummary(
            total_categories=len(comparison_rows),
            matched_count=sum(1 for r in comparison_rows if r.status == "MATCH"),
            variance_count=sum(1 for r in comparison_rows if r.status == "VARIANCE"),
            new_count=sum(1 for r in comparison_rows if r.status == "NEW"),
            missing_count=sum(1 for r in comparison_rows if r.status == "MISSING"),
            overall_status=verification.status,
        )

        output = OrchestratorOutput(
            partner_name=state.input.partner_name,
            filename=state.input.filename,
            document_id=document_id,
            verification=verification,
            risk=risk,
            header=flat_header,
            models=flat_models,
            rates=flat_rates,
            commitments=flat_commitments,
            field_details=verification.field_details,
            total_fields=total_fields,
            comparison_table=comparison_rows,
            summary=summary,
            extraction_data=state.extraction_result if state.extraction_result else {},
            verification_data=(
                state.verification_result.model_dump()
                if state.verification_result
                else None
            ),
            risk_data=state.risk_result.model_dump() if state.risk_result else None,
            errors=errors,
            raw_extraction=state.extraction_result or {},
        )

        logger.info(f"Combined results: {len(review_table)} rows in review table")

        return {"output": output}

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)

        builder.add_node("extraction", self._extraction_node)
        builder.add_node("verification", self._verification_node)
        builder.add_node("risk", self._risk_node)
        builder.add_node(
            "parallel_verification_risk", self._run_verification_and_risk_parallel
        )
        builder.add_node("ai_notes", self._ai_notes_node)
        builder.add_node("combine_results", self._combine_results_node)

        builder.set_entry_point("extraction")
        # Use parallel processing for verification and risk (comment out sequential version)
        # builder.add_edge("extraction", "verification")
        # builder.add_edge("verification", "risk")
        builder.add_edge("extraction", "parallel_verification_risk")
        builder.add_edge("parallel_verification_risk", "ai_notes")
        builder.add_edge("ai_notes", "combine_results")
        builder.add_edge("combine_results", END)

        return builder.compile()

    def run(self, payload: OrchestratorInput) -> OrchestratorOutput:
        """
        Execute the orchestrator workflow.

        Args:
            payload: OrchestratorInput with PDF data and metadata

        Returns:
            OrchestratorOutput with combined results for manual review
        """
        logger.info(f"Starting orchestrator workflow for {payload.filename}")

        # Initialize state
        initial_state = OrchestratorState(input=payload)

        # Execute the workflow directly so patched node methods in tests are honored.
        state = initial_state
        for node in (
            self._extraction_node,
            self._verification_node,
            self._risk_node,
            self._ai_notes_node,
        ):
            updates = node(state)
            if updates:
                state = state.model_copy(update=updates)

        combined = self._combine_results_node(state)
        output = combined.get("output") if isinstance(combined, dict) else None

        if output:
            logger.info(f"Orchestrator workflow completed for {payload.filename}")
        else:
            logger.error(f"Orchestrator workflow failed for {payload.filename}")
            # Return empty output on failure
            output = OrchestratorOutput(
                review_table=[],
                summary=ReviewSummary(
                    total_rows=0,
                    changed_rows=0,
                    flagged_rows=0,
                    highest_risk="LOW",
                    recommendation="Workflow failed",
                ),
                extraction_data={},
                errors={"workflow": "Failed to produce output"},
            )

        return output
