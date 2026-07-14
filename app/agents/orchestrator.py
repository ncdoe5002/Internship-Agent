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
import re
from difflib import SequenceMatcher
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from .extraction_agent import ExtractionAgent, ExtractionAgentInput
from .verification_agent import (
    VerificationAgent,
    VerificationAgentInput,
    VerificationResult,
)
from .risk_agent import RiskAgent, RiskAgentInput, RiskItem, RiskSummary

logger = logging.getLogger(__name__)


class OrchestratorInput(BaseModel):
    """Input schema for the orchestrator."""

    pdf_bytes: bytes
    filename: str
    partner_name: str
    baseline_data: dict | None = None
    file_type: str = "pdf"


class OrchestratorState(BaseModel):
    """State passed between nodes in the LangGraph workflow."""

    input: OrchestratorInput
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


ai_notes_parser = PydanticOutputParser(pydantic_object=AINotesResult)
ai_notes_prompt = ChatPromptTemplate.from_template(
    "Given these flagged tariff rate changes:\n{items}\n\n"
    "For each item, explain in one sentence why it was flagged and what "
    "the risk level means for approval.\n{format_instructions}"
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

    def _build_graph(self):
        """
        Build the LangGraph workflow.

        Workflow:
        - extraction_node: Runs ExtractionAgent
        - verification_node: Runs VerificationAgent (parallel with risk)
        - risk_node: Runs RiskAgent (parallel with verification)
        - ai_notes_node: Adds AI notes to non-LOW risk rows
        - combine_results_node: Merges all results into tabular format

        Edges:
        - extraction → verification
        - extraction → risk
        - verification → combine_results
        - risk → ai_notes
        - ai_notes → combine_results
        """
        workflow = StateGraph(OrchestratorState)

        # Add nodes
        workflow.add_node("extraction", self._extraction_node)
        workflow.add_node("verification", self._verification_node)
        workflow.add_node("risk", self._risk_node)
        workflow.add_node("ai_notes", self._ai_notes_node)
        workflow.add_node("combine_results", self._combine_results_node)

        # Set entry point
        workflow.set_entry_point("extraction")

        # Add edges for parallel execution
        workflow.add_edge("extraction", "verification")
        workflow.add_edge("extraction", "risk")
        workflow.add_edge("verification", "combine_results")
        workflow.add_edge("risk", "ai_notes")
        workflow.add_edge("ai_notes", "combine_results")
        workflow.add_edge("combine_results", END)

        return workflow.compile()

    def _normalize_category(self, category: str) -> str:
        """
        Normalize category string for matching.

        Args:
            category: Raw category string

        Returns:
            Normalized category string (lowercase, trimmed, collapsed whitespace)
        """
        if not category:
            return ""
        return re.sub(r"\s+", " ", str(category).lower().strip())

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

        # Remove currency symbols and thousand separators
        cleaned = re.sub(r"[\$€£¥,\s]", "", rate_str)

        # Remove trailing units (e.g., "0.05/min", "0.10 per minute")
        cleaned = re.sub(r"\s*(?:per|\/|).*$", "", cleaned, flags=re.IGNORECASE)

        try:
            return float(cleaned)
        except (ValueError, TypeError):
            logger.warning(
                f"Failed to parse rate: '{rate_str}' -> cleaned: '{cleaned}'"
            )
            return None

    def _find_column_indices(self, headers: list[str]) -> tuple[int | None, int | None]:
        """
        Find column indices for category and rate based on headers.

        Args:
            headers: List of header names

        Returns:
            Tuple of (category_index, rate_index) or (None, None) if not found
        """
        category_idx = None
        rate_idx = None

        normalized_headers = [self._normalize_category(h) for h in headers]

        # Category column keywords
        category_keywords = [
            "category",
            "service",
            "type",
            "description",
            "item",
            "name",
        ]
        for idx, header in enumerate(normalized_headers):
            if any(keyword in header for keyword in category_keywords):
                category_idx = idx
                break

        # Rate column keywords
        rate_keywords = ["rate", "price", "cost", "tariff", "amount", "fee", "charge"]
        for idx, header in enumerate(normalized_headers):
            if any(keyword in header for keyword in rate_keywords):
                rate_idx = idx
                break

        # Fallback: assume first column is category, second is rate if not found
        if category_idx is None and len(headers) >= 1:
            category_idx = 0
            logger.warning(
                "Could not identify category column by headers, defaulting to index 0"
            )

        if rate_idx is None and len(headers) >= 2:
            rate_idx = 1
            logger.warning(
                "Could not identify rate column by headers, defaulting to index 1"
            )

        return category_idx, rate_idx

    def _extraction_node(self, state: OrchestratorState) -> dict:
        """
        Run ExtractionAgent to extract tariff tables from document.

        Args:
            state: Current orchestrator state

        Returns:
            Updated state with extraction result or error
        """
        try:
            logger.info(
                f"Starting extraction for {state.input.filename} (type: {state.input.file_type})"
            )

            payload = ExtractionAgentInput(
                document_types=state.input.pdf_bytes,
                filename=state.input.filename,
                file_type=state.input.file_type,
            )

            result = self.extraction_agent.run(payload)

            logger.info(f"Extraction completed successfully for {state.input.filename}")

            return {"extraction_result": result.model_dump(), "extraction_error": None}
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
        try:
            if state.extraction_result is None:
                logger.warning("Skipping verification: extraction failed")
                return {
                    "verification_result": None,
                    "verification_error": "Skipped due to extraction failure",
                }

            logger.info(f"Starting verification for {state.input.partner_name}")

            payload = VerificationAgentInput(
                partner_name=state.input.partner_name,
                extracted_tables=state.extraction_result,
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

    def _risk_node(self, state: OrchestratorState) -> dict:
        """
        Run RiskAgent to assess risk of rate changes.

        Args:
            state: Current orchestrator state

        Returns:
            Updated state with risk result or error
        """
        try:
            if state.extraction_result is None:
                logger.warning("Skipping risk assessment: extraction failed")
                return {
                    "risk_result": None,
                    "risk_error": "Skipped due to extraction failure",
                }

            logger.info(f"Starting risk assessment for {state.input.partner_name}")

            # Convert extraction result to comparison rows for risk assessment
            comparison_rows = self._extract_comparison_rows(
                state.extraction_result, state.input.baseline_data
            )

            # Use verification confidence if available, default to 95
            confidence = (
                state.verification_result.confidence
                if state.verification_result
                else 95
            )

            payload = RiskAgentInput(
                partner_name=state.input.partner_name,
                confidence=confidence,
                comparison_rows=comparison_rows,
            )

            result = self.risk_agent.assess(payload)

            logger.info(f"Risk assessment completed for {state.input.partner_name}")

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
        if not state.risk_result or not state.risk_result.items:
            return {"risk_result": state.risk_result}

        flagged = [i for i in state.risk_result.items if i.risk_level != "LOW"]
        if not flagged:
            return {"risk_result": state.risk_result}

        chain = ai_notes_prompt | self.model | ai_notes_parser
        try:
            result = chain.invoke(
                {
                    "items": [i.model_dump() for i in flagged],
                    "format_instructions": ai_notes_parser.get_format_instructions(),
                }
            )
            notes_by_category = {n.category: n.note for n in result.notes}
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

        # Process extracted tables
        for table_idx, table in enumerate(tables):
            headers = table.get("headers", [])
            rows = table.get("rows", [])

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
            summary = ReviewSummary(
                total_rows=state.risk_result.total_rows,
                changed_rows=state.risk_result.changed_rows,
                flagged_rows=state.risk_result.flagged_rows,
                highest_risk=state.risk_result.highest_risk,
                recommendation=state.risk_result.recommendation,
            )
        else:
            summary = ReviewSummary(
                total_rows=0,
                changed_rows=0,
                flagged_rows=0,
                highest_risk="LOW",
                recommendation="Unable to assess - risk analysis failed",
            )

        # Collect errors
        errors = {}
        if state.extraction_error:
            errors["extraction"] = state.extraction_error
        if state.verification_error:
            errors["verification"] = state.verification_error
        if state.risk_error:
            errors["risk"] = state.risk_error

        # Build output
        output = OrchestratorOutput(
            review_table=review_table,
            summary=summary,
            extraction_data=state.extraction_result if state.extraction_result else {},
            verification_data=(
                state.verification_result.model_dump()
                if state.verification_result
                else None
            ),
            risk_data=state.risk_result.model_dump() if state.risk_result else None,
            errors=errors,
        )

        logger.info(f"Combined results: {len(review_table)} rows in review table")

        return {"output": output}

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

        # Run the workflow
        final_state = self.graph.invoke(initial_state)

        # Extract output
        output = final_state.get("output")

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
