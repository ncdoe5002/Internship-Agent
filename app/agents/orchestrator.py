"""
Orchestrator for coordinating ExtractionAgent, VerificationAgent, and RiskAgent.
Integrates friend's extractors.py logic seamlessly with LangGraph execution graph.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

# Local client and friend's extractor functions
from app.services.extractors import extract_generic_document, extract_roaming_agreement
from app.services.llm_client import chat_complete_json

from .risk_agent import RiskAgent, RiskAgentInput, RiskItem, RiskSummary
from .verification_agent import (
    VerificationAgent,
    VerificationAgentInput,
    VerificationResult,
)

logger = logging.getLogger(__name__)


# --- Input / Output / State Models ---


class OrchestratorInput(BaseModel):
    pdf_bytes: bytes
    filename: str
    partner_name: str
    raw_doc_text: (
        str  # Document text passed into friend's extractor & verification grounding
    )
    baseline_data: dict | None = None
    file_type: str = "pdf"
    use_telecom_prompt: bool = True


class ReviewTableRow(BaseModel):
    category: str
    proposed_rate: float | str | None = None
    baseline_rate: float | str | None = None
    pct_change: float | None = None
    status: Literal["MATCH", "VARIANCE", "NEW", "MISSING"] = "MATCH"
    flag: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    ai_note: str | None = None


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
    verification: VerificationResult
    risk: RiskSummary
    comparison_table: list[ReviewTableRow] = Field(default_factory=list)
    summary: ReviewSummary = Field(default_factory=ReviewSummary)
    errors: list[str] = Field(default_factory=list)


class OrchestratorState(BaseModel):
    input: OrchestratorInput | None = None
    extraction_result: dict | None = None
    verification_result: VerificationResult | None = None
    risk_result: RiskSummary | None = None
    orchestrator_output: OrchestratorOutput | None = None
    extraction_error: str | None = None
    verification_error: str | None = None
    risk_error: str | None = None


# --- Orchestrator Class ---


class Orchestrator:
    def __init__(self):
        self.verification_agent = VerificationAgent()
        self.risk_agent = RiskAgent()
        self.graph = self._build_graph()

    def _adapt_staging_schema(self, raw_extraction: dict) -> dict:
        """
        Adapts friend's relational staging tables output into an array of generic JSON tables.
        This maintains compatibility with VerificationAgent and RiskAgent algorithms.
        """
        if "tables" in raw_extraction:
            return raw_extraction

        adapted_tables = []
        for table_name, content in raw_extraction.items():
            if isinstance(content, list) and len(content) > 0:
                # Deduce headers from key elements of first dictionary
                first_row = content[0]
                if isinstance(first_row, dict):
                    headers = list(first_row.keys())
                    rows = [
                        [str(row_dict.get(h, "")) for h in headers]
                        for row_dict in content
                    ]
                    adapted_tables.append(
                        {"title": table_name, "headers": headers, "rows": rows}
                    )
            elif isinstance(content, dict):
                # Single object record turned into a two-column key/value table
                headers = ["FIELD", "VALUE"]
                rows = [[str(k), str(v)] for k, v in content.items()]
                adapted_tables.append(
                    {"title": table_name, "headers": headers, "rows": rows}
                )

        return {"tables": adapted_tables}

    # --- Utility Methods for Downstream Risk & Comparison ---

    def _normalize_category(self, cat: str) -> str:
        s = cat.strip().lower()
        s = re.sub(r"[\/\_\-\s]+", " ", s)
        return s.strip()

    def _fuzzy_match_category(
        self, target: str, candidates: list[str], threshold: float = 0.75
    ) -> str | None:
        target_norm = self._normalize_category(target)
        best_match = None
        best_ratio = 0.0

        for cand in candidates:
            cand_norm = self._normalize_category(cand)
            ratio = SequenceMatcher(None, target_norm, cand_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = cand

        return best_match if best_ratio >= threshold else None

    def _parse_rate(self, val: Any) -> float | None:
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.lower() == "null":
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
        self, extracted_tables: dict | None, baseline_data: dict | None
    ) -> list[ReviewTableRow]:
        rows: list[ReviewTableRow] = []
        extracted_map: dict[str, float | None] = {}

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
                        if cat_str:
                            extracted_map[cat_str] = rate_val

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

        for ext_cat, ext_rate in extracted_map.items():
            match_key = self._fuzzy_match_category(ext_cat, list(baseline_map.keys()))

            if match_key:
                matched_baseline_keys.add(match_key)
                base_rate = baseline_map[match_key]

                if ext_rate is not None and base_rate is not None and base_rate != 0:
                    pct = round(((ext_rate - base_rate) / base_rate) * 100, 2)
                else:
                    pct = None

                status = "MATCH" if ext_rate == base_rate else "VARIANCE"
                flag = "LOW"
                if status == "VARIANCE" and pct is not None:
                    if abs(pct) > 20:
                        flag = "HIGH"
                    elif abs(pct) > 5:
                        flag = "MEDIUM"

                rows.append(
                    ReviewTableRow(
                        category=ext_cat,
                        proposed_rate=ext_rate,
                        baseline_rate=base_rate,
                        pct_change=pct,
                        status=status,
                        flag=flag,
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
                    )
                )

        return rows

    # --- Graph Execution Nodes ---

    def _extraction_node(self, state: OrchestratorState) -> dict:
        if state.input is None or not state.input.raw_doc_text:
            return {
                "extraction_result": None,
                "extraction_error": "Input payload or document text missing",
            }
        try:
            # Delegate directly to friend's extractor logic
            if state.input.use_telecom_prompt:
                raw_extracted = extract_roaming_agreement(state.input.raw_doc_text)
            else:
                raw_extracted = extract_generic_document(state.input.raw_doc_text)

            adapted_result = self._adapt_staging_schema(raw_extracted)

            return {
                "extraction_result": adapted_result,
                "extraction_error": None,
            }
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            return {"extraction_result": None, "extraction_error": str(e)}

    def _verification_node(self, state: OrchestratorState) -> dict:
        if state.input is None:
            return {
                "verification_result": None,
                "verification_error": "Input payload missing",
            }
        try:
            if state.extraction_result is None:
                return {
                    "verification_result": None,
                    "verification_error": "Skipped due to extraction failure",
                }

            payload = VerificationAgentInput(
                partner_name=state.input.partner_name,
                extracted_tables=state.extraction_result,
                raw_doc_text=state.input.raw_doc_text,
                baseline_tables=state.input.baseline_data,
            )
            result = self.verification_agent.run(payload)
            return {"verification_result": result, "verification_error": None}
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            return {"verification_result": None, "verification_error": str(e)}

    def _risk_node(self, state: OrchestratorState) -> dict:
        if state.input is None or state.verification_result is None:
            return {
                "risk_result": None,
                "risk_error": "Input or verification missing for risk evaluation",
            }

        try:
            comparison_rows = self._extract_comparison_rows(
                state.extraction_result, state.input.baseline_data
            )

            risk_items = [
                RiskItem(
                    category=r.category,
                    proposed_rate=r.proposed_rate,
                    baseline_rate=r.baseline_rate,
                    pct_change=r.pct_change,
                    risk_level=r.flag,
                )
                for r in comparison_rows
            ]

            risk_input = RiskAgentInput(
                confidence=state.verification_result.confidence,
                items=risk_items,
            )

            result = self.risk_agent.run(risk_input)
            return {"risk_result": result, "risk_error": None}
        except Exception as e:
            logger.error(f"Risk assessment failed: {str(e)}")
            return {"risk_result": None, "risk_error": str(e)}

    def _ai_notes_node(self, state: OrchestratorState) -> dict:
        if not state.risk_result or not state.risk_result.items:
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
            notes_list = result.get("notes", [])
            notes_by_category = {
                n.get("category"): n.get("note")
                for n in notes_list
                if n.get("category")
            }

            for item in state.risk_result.items:
                if item.category in notes_by_category:
                    item.note = notes_by_category[item.category]
        except Exception as e:
            logger.warning(
                f"AI notes generation failed: {e}. Defaulting to standard response."
            )

        return {"risk_result": state.risk_result}

    def _combine_results_node(self, state: OrchestratorState) -> dict:
        if state.input is None:
            return {"orchestrator_output": None}

        errors = []
        if state.extraction_error:
            errors.append(f"Extraction Error: {state.extraction_error}")
        if state.verification_error:
            errors.append(f"Verification Error: {state.verification_error}")
        if state.risk_error:
            errors.append(f"Risk Error: {state.risk_error}")

        verification = state.verification_result or VerificationResult(
            status="FAILED",
            confidence=0,
            checks=[],
            issues=["Verification stage failed"],
        )

        risk = state.risk_result or RiskSummary(
            overall_risk="HIGH",
            summary="Assessment incomplete due to errors",
            items=[],
        )

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
            verification=verification,
            risk=risk,
            comparison_table=comparison_rows,
            summary=summary,
            errors=errors,
        )

        return {"orchestrator_output": output}

    # --- Graph Wiring ---

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)

        builder.add_node("extraction", self._extraction_node)
        builder.add_node("verification", self._verification_node)
        builder.add_node("risk", self._risk_node)
        builder.add_node("ai_notes", self._ai_notes_node)
        builder.add_node("combine_results", self._combine_results_node)

        builder.set_entry_point("extraction")
        builder.add_edge("extraction", "verification")
        builder.add_edge("verification", "risk")
        builder.add_edge("risk", "ai_notes")
        builder.add_edge("ai_notes", "combine_results")
        builder.add_edge("combine_results", END)

        return builder.compile()

    def run(self, input_payload: OrchestratorInput) -> OrchestratorOutput:
        initial_state = OrchestratorState(input=input_payload)
        final_state = self.graph.invoke(initial_state)

        if isinstance(final_state, dict):
            output = final_state.get("orchestrator_output")
        else:
            output = getattr(final_state, "orchestrator_output", None)

        if output is None:
            raise RuntimeError("Pipeline failed to generate OrchestratorOutput.")

        return output
