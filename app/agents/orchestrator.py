"""
Orchestrator for coordinating ExtractionAgent, VerificationAgent, and RiskAgent.
Integrates friend's extractors.py logic seamlessly with LangGraph execution graph.
"""

from __future__ import annotations

import logging
import re, os
from difflib import SequenceMatcher
from typing import Any, Literal

from langgraph.graph import END, StateGraph
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


# --- Input / Output / State Models ---


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
            pre_extracted = state.input.pre_extracted or state.input.pre_extracted_data
            if pre_extracted:
                adapted_result = self._adapt_staging_schema(pre_extracted)
                return {"extraction_result": adapted_result, "extraction_error": None}

            # Fallback: run Docling if pre_extracted not provided
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            header, model, normal_model, commitment = get_contents(
                filePath=state.input.file_path,
                use_ocr=True,
                api_key=api_key,
            )
            raw_extracted = {
                "header": header.model_dump() if header else {},
                "model": [model.model_dump()] if model else [],
                "normal_model": [normal_model.model_dump()] if normal_model else [],
                "commitment": [commitment.model_dump()] if commitment else [],
            }
            adapted_result = self._adapt_staging_schema(raw_extracted)
            return {"extraction_result": adapted_result, "extraction_error": None}
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
            errors=errors,
            raw_extraction=state.extraction_result or {},
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
