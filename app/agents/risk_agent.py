"""
Risk Agent - Assesses risk levels for tariff changes.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


class RiskConfig(BaseModel):
    """Configuration parameters for risk assessment."""
    high_variance_threshold: float = 20.0
    low_confidence_threshold: float = 0.65
    financial_field_weight: float = 1.5
    moderate_variance_threshold: float = 5.0


class ReviewTableRow(BaseModel):
    category: str
    proposed_rate: float | str | None = None
    baseline_rate: float | str | None = None
    pct_change: float | None = None
    status: Literal["MATCH", "VARIANCE", "NEW", "MISSING"] = "MATCH"
    flag: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    ai_note: str | None = None
    confidence_score: float = 1.0  # Added field with a default fallbacck


class RiskItem(BaseModel):
    category: str = Field(description="Category or classification of the tariff item")
    old_rate: float = Field(description="Original tariff rate")
    new_rate: float = Field(description="New tariff rate")
    delta_pct: float = Field(description="Percentage change between rates")
    risk_level: RiskLevel = Field(default="LOW", description="Assessed risk level")
    note: str = Field(default="", description="Additional notes or context")


class RiskAgentInput(BaseModel):
    partner_name: str = Field(description="Name of the partner organization")
    confidence: int = Field(
        ge=0, le=100, description="Confidence score from verification (0-100)"
    )
    comparison_rows: list[ReviewTableRow] = Field(
        description="List of rate comparison rows from Orchestrator"
    )


class RiskSummary(BaseModel):
    partner_name: str = Field(description="Name of the partner organization")
    total_rows: int = Field(description="Total number of tariff rows analyzed")
    changed_rows: int = Field(description="Number of rows with rate changes")
    flagged_rows: int = Field(description="Number of rows with MEDIUM or HIGH risk")
    highest_risk: RiskLevel = Field(description="Highest risk level found")
    recommendation: str = Field(description="Action recommendation based on assessment")
    items: list[RiskItem] = Field(
        default_factory=list, description="Full list of assessed risk items"
    )


class RiskAgent:
    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def assess(self, payload: RiskAgentInput) -> RiskSummary:
        total_rows = len(payload.comparison_rows)
        changed_rows = sum(
            1 for row in payload.comparison_rows if row.status in ("VARIANCE", "NEW")
        )

        risk_items: list[RiskItem] = []

        # --- PLACE THE LOOP HERE ---
        for row in payload.comparison_rows:
            # Handle MISSING rows explicitly - absence is a validation flag, not a -100% rate change
            if row.status == "MISSING":
                risk_level: RiskLevel = "MEDIUM"
                note = "Field missing from extraction - validation flag, not a rate change."
                risk_items.append(
                    RiskItem(
                        category=row.category,
                        old_rate=float(row.baseline_rate) if row.baseline_rate is not None else 0.0,
                        new_rate=0.0,
                        delta_pct=0.0,
                        risk_level=risk_level,
                        note=note,
                    )
                )
                continue

            # Use pct_change from orchestrator if available, otherwise recompute
            if row.pct_change is not None:
                delta = row.pct_change
                old_val = (
                    float(row.baseline_rate)
                    if row.baseline_rate is not None
                    and str(row.baseline_rate).strip() != ""
                    else 0.0
                )
                new_val = (
                    float(row.proposed_rate)
                    if row.proposed_rate is not None
                    and str(row.proposed_rate).strip() != ""
                    else 0.0
                )
            else:
                try:
                    old_val = (
                        float(row.baseline_rate)
                        if row.baseline_rate is not None
                        and str(row.baseline_rate).strip() != ""
                        else 0.0
                    )
                    new_val = (
                        float(row.proposed_rate)
                        if row.proposed_rate is not None
                        and str(row.proposed_rate).strip() != ""
                        else 0.0
                    )
                    delta = (
                        round(((new_val - old_val) / old_val) * 100, 2)
                        if old_val != 0
                        else 0.0
                    )
                except (ValueError, TypeError):
                    old_val, new_val, delta = 0.0, 0.0, 0.0

            # Determine Risk Level based on Variance & Cell Confidence
            # Logic: Check delta magnitude first, then confidence. This ensures moderate_variance_threshold
            # actually gates a distinct risk level from the generic "VARIANCE or NEW" case.
            # - HIGH: VARIANCE with abs(delta) > high_variance_threshold (20%)
            # - MEDIUM: VARIANCE with abs(delta) > moderate_variance_threshold (5%) OR low confidence
            # - LOW: Everything else (MATCH, small variance, good confidence)
            is_financial_field = any(
                keyword in row.category.lower()
                for keyword in ["amount", "commitment", "revenue", "cost"]
            )
            confidence_threshold = (
                self.config.low_confidence_threshold * self.config.financial_field_weight
                if is_financial_field
                else self.config.low_confidence_threshold
            )

            if row.status == "VARIANCE" and abs(delta) > self.config.high_variance_threshold:
                risk_level: RiskLevel = "HIGH"
                note = f"High rate shift detected ({delta}% variance)."
            elif (
                row.status == "VARIANCE"
                and abs(delta) > self.config.moderate_variance_threshold
            ) or row.confidence_score < confidence_threshold:
                risk_level = "MEDIUM"
                note = (
                    row.ai_note
                    or f"Moderate variance or low confidence cell ({int(row.confidence_score * 100)}%)."
                )
            else:
                risk_level = "LOW"
                note = row.ai_note or ""

            # Append the calculated items to your list
            risk_items.append(
                RiskItem(
                    category=row.category,
                    old_rate=old_val,
                    new_rate=new_val,
                    delta_pct=delta,
                    risk_level=risk_level,
                    note=note,
                )
            )

        # --- CONTINUATION OF ASSESS METHOD ---
        flagged_rows = sum(1 for item in risk_items if item.risk_level != "LOW")

        if any(item.risk_level == "HIGH" for item in risk_items):
            highest_risk: RiskLevel = "HIGH"
        elif any(item.risk_level == "MEDIUM" for item in risk_items):
            highest_risk = "MEDIUM"
        else:
            highest_risk = "LOW"

        if payload.confidence < 70 or highest_risk == "HIGH":
            recommendation = "Manager approval required"
        elif payload.confidence < 90 or flagged_rows > 0:
            recommendation = "Review recommended before approval"
        else:
            recommendation = "Safe to proceed"

        return RiskSummary(
            partner_name=payload.partner_name,
            total_rows=total_rows,
            changed_rows=changed_rows,
            flagged_rows=flagged_rows,
            highest_risk=highest_risk,
            recommendation=recommendation,
            items=risk_items,
        )
