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
    comparison_rows: list[RiskItem] = Field(
        description="List of rate changes to assess"
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
        changed_rows = sum(
            1 for row in payload.comparison_rows if row.old_rate != row.new_rate
        )
        flagged_rows = sum(
            1 for row in payload.comparison_rows if row.risk_level != "LOW"
        )

        if any(row.risk_level == "HIGH" for row in payload.comparison_rows):
            highest_risk: RiskLevel = "HIGH"
        elif any(row.risk_level == "MEDIUM" for row in payload.comparison_rows):
            highest_risk = "MEDIUM"
        else:
            highest_risk = "LOW"

        if payload.confidence < 90 or highest_risk == "HIGH":
            recommendation = "Manager approval required"
        elif flagged_rows > 0:
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
            items=payload.comparison_rows,
        )
