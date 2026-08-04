"""
Risk Agent - Assesses risk levels for tariff changes.

This agent analyzes tariff rate changes and assesses the risk level for each change.
It provides a summary with recommendations on whether the changes require
manager approval, review, or can proceed safely.

Usage:
    agent = RiskAgent()
    summary = agent.assess(payload)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from orchestrator import ReviewTableRow

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


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
    def assess(self, payload: RiskAgentInput) -> RiskSummary:
        total_rows = len(payload.comparison_rows)

        # Track changed/flagged rows using ReviewTableRow status
        changed_rows = sum(
            1 for row in payload.comparison_rows if row.status in ("VARIANCE", "NEW")
        )

        # Calculate risk per item if not already set
        risk_items: list[RiskItem] = []
        for row in payload.comparison_rows:
            # Parse values safely
            try:
                old_val = float(row.baseline_value)
                new_val = float(row.uploaded_value)
                delta = (
                    round(((new_val - old_val) / old_val) * 100, 2)
                    if old_val != 0
                    else 0.0
                )
            except (ValueError, TypeError):
                old_val, new_val, delta = 0.0, 0.0, 0.0

            # Determine Risk Level based on Variance & Cell Confidence
            if row.status == "VARIANCE" and abs(delta) > 20.0:
                risk_level: RiskLevel = "HIGH"
                note = f"High rate shift detected ({delta}% variance)."
            elif row.status in ("VARIANCE", "NEW") or row.confidence_score < 0.65:
                risk_level = "MEDIUM"
                note = (
                    row.ai_note
                    or f"Moderate variance or low confidence cell ({int(row.confidence_score*100)}%)."
                )
            else:
                risk_level = "LOW"
                note = "Rate matches baseline standard."

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

        flagged_rows = sum(1 for item in risk_items if item.risk_level != "LOW")

        if any(item.risk_level == "HIGH" for item in risk_items):
            highest_risk: RiskLevel = "HIGH"
        elif any(item.risk_level == "MEDIUM" for item in risk_items):
            highest_risk = "MEDIUM"
        else:
            highest_risk = "LOW"

        # Recommendation logic aligned with Verification thresholds
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
