"""
Orchestrator for coordinating ExtractionAgent, VerificationAgent, and RiskAgent using LangGraph.

This module implements a LangGraph-based workflow that:
1. Runs ExtractionAgent to extract tariff tables from PDF
2. Runs VerificationAgent and RiskAgent in parallel after extraction
3. Combines results into a tabular format for manual review
4. Handles individual agent failures with graceful degradation
"""

import logging
from typing import Any, Literal

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from .extraction_agent import ExtractionAgent, ExtractionAgentInput
from .verification_agent import VerificationAgent, VerificationAgentInput, VerificationResult
from .risk_agent import RiskAgent, RiskAgentInput, RiskItem, RiskSummary

logger = logging.getLogger(__name__)


class OrchestratorInput(BaseModel):
    """Input schema for the orchestrator."""
    pdf_bytes: bytes
    filename: str
    partner_name: str
    baseline_data: dict | None = None


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


class ReviewSummary(BaseModel):
    """Summary statistics for the review table."""
    total_rows: int
    changed_rows: int
    flagged_rows: int
    highest_risk: Literal["LOW", "MEDIUM", "HIGH"]
    recommendation: str


class OrchestratorOutput(BaseModel):
    """Output schema for the orchestrator with tabular review data."""
    review_table: list[ReviewTableRow]
    summary: ReviewSummary
    extraction_data: dict
    verification_data: dict | None = None
    risk_data: dict | None = None
    errors: dict[str, str] = Field(default_factory=dict)


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

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow.
        
        Workflow:
        - extraction_node: Runs ExtractionAgent
        - verification_node: Runs VerificationAgent (parallel with risk)
        - risk_node: Runs RiskAgent (parallel with verification)
        - combine_results_node: Merges all results into tabular format
        
        Edges:
        - extraction → verification
        - extraction → risk
        - verification → combine_results
        - risk → combine_results
        """
        workflow = StateGraph(OrchestratorState)

        # Add nodes
        workflow.add_node("extraction", self._extraction_node)
        workflow.add_node("verification", self._verification_node)
        workflow.add_node("risk", self._risk_node)
        workflow.add_node("combine_results", self._combine_results_node)

        # Set entry point
        workflow.set_entry_point("extraction")

        # Add edges for parallel execution
        workflow.add_edge("extraction", "verification")
        workflow.add_edge("extraction", "risk")
        workflow.add_edge("verification", "combine_results")
        workflow.add_edge("risk", "combine_results")
        workflow.add_edge("combine_results", END)

        return workflow.compile()

    def _extraction_node(self, state: OrchestratorState) -> dict:
        """
        Run ExtractionAgent to extract tariff tables from PDF.
        
        Args:
            state: Current orchestrator state
            
        Returns:
            Updated state with extraction result or error
        """
        try:
            logger.info(f"Starting extraction for {state.input.filename}")
            
            payload = ExtractionAgentInput(
                document_types=state.input.pdf_bytes,
                filename=state.input.filename
            )
            
            result = self.extraction_agent.run(payload)
            
            logger.info(f"Extraction completed successfully for {state.input.filename}")
            
            return {
                "extraction_result": result.model_dump(),
                "extraction_error": None
            }
        except Exception as e:
            logger.error(f"Extraction failed for {state.input.filename}: {str(e)}")
            return {
                "extraction_result": None,
                "extraction_error": str(e)
            }

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
                    "verification_error": "Skipped due to extraction failure"
                }
            
            logger.info(f"Starting verification for {state.input.partner_name}")
            
            payload = VerificationAgentInput(
                partner_name=state.input.partner_name,
                extracted_tables=state.extraction_result,
                baseline_tables=state.input.baseline_data
            )
            
            result = self.verification_agent.run(payload)
            
            logger.info(f"Verification completed for {state.input.partner_name}")
            
            return {
                "verification_result": result,
                "verification_error": None
            }
        except Exception as e:
            logger.error(f"Verification failed for {state.input.partner_name}: {str(e)}")
            return {
                "verification_result": None,
                "verification_error": str(e)
            }

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
                    "risk_error": "Skipped due to extraction failure"
                }
            
            logger.info(f"Starting risk assessment for {state.input.partner_name}")
            
            # Convert extraction result to comparison rows for risk assessment
            comparison_rows = self._extract_comparison_rows(
                state.extraction_result,
                state.input.baseline_data
            )
            
            # Use verification confidence if available, default to 95
            confidence = state.verification_result.confidence if state.verification_result else 95
            
            payload = RiskAgentInput(
                partner_name=state.input.partner_name,
                confidence=confidence,
                comparison_rows=comparison_rows
            )
            
            result = self.risk_agent.assess(payload)
            
            logger.info(f"Risk assessment completed for {state.input.partner_name}")
            
            return {
                "risk_result": result,
                "risk_error": None
            }
        except Exception as e:
            logger.error(f"Risk assessment failed for {state.input.partner_name}: {str(e)}")
            return {
                "risk_result": None,
                "risk_error": str(e)
            }

    def _extract_comparison_rows(
        self,
        extraction_result: dict,
        baseline_data: dict | None
    ) -> list[RiskItem]:
        """
        Convert extraction result to RiskItem comparison rows.
        
        Args:
            extraction_result: Extraction result from ExtractionAgent
            baseline_data: Baseline tariff data for comparison
            
        Returns:
            List of RiskItem objects for risk assessment
        """
        comparison_rows = []
        
        # Extract tables from extraction result
        tables = extraction_result.get("tables", [])
        
        for table in tables:
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            
            # Try to identify rate columns (simplified approach)
            # In production, this would be more sophisticated
            for row in rows:
                if len(row) >= 2:
                    try:
                        # Assume first column is category, second is rate
                        category = row[0]
                        new_rate = float(row[1]) if row[1] else 0.0
                        
                        # Get baseline rate if available
                        old_rate = 0.0
                        if baseline_data:
                            # Simple lookup - in production would be more sophisticated
                            for baseline_table in baseline_data.get("tables", []):
                                for baseline_row in baseline_table.get("rows", []):
                                    if baseline_row[0] == category:
                                        old_rate = float(baseline_row[1]) if len(baseline_row) > 1 else 0.0
                                        break
                        
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
                        
                        note = ""
                        if delta_pct > 0:
                            note = f"Rate increased by {delta_pct:.1f}%"
                        elif delta_pct < 0:
                            note = f"Rate decreased by {abs(delta_pct):.1f}%"
                        
                        comparison_rows.append(RiskItem(
                            category=category,
                            old_rate=old_rate,
                            new_rate=new_rate,
                            delta_pct=delta_pct,
                            risk_level=risk_level,
                            note=note
                        ))
                    except (ValueError, IndexError):
                        # Skip rows that can't be parsed
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
                verification_status = "READY"
                if state.verification_result:
                    verification_status = state.verification_result.status
                
                review_table.append(ReviewTableRow(
                    category=item.category,
                    old_rate=item.old_rate,
                    new_rate=item.new_rate,
                    delta_pct=item.delta_pct,
                    risk_level=item.risk_level,
                    ai_notes=item.note,
                    verification_status=verification_status
                ))
        
        # Build summary
        if state.risk_result:
            summary = ReviewSummary(
                total_rows=state.risk_result.total_rows,
                changed_rows=state.risk_result.changed_rows,
                flagged_rows=state.risk_result.flagged_rows,
                highest_risk=state.risk_result.highest_risk,
                recommendation=state.risk_result.recommendation
            )
        else:
            summary = ReviewSummary(
                total_rows=0,
                changed_rows=0,
                flagged_rows=0,
                highest_risk="LOW",
                recommendation="Unable to assess - risk analysis failed"
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
            verification_data=state.verification_result.model_dump() if state.verification_result else None,
            risk_data=state.risk_result.model_dump() if state.risk_result else None,
            errors=errors
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
                    recommendation="Workflow failed"
                ),
                extraction_data={},
                errors={"workflow": "Failed to produce output"}
            )
        
        return output
