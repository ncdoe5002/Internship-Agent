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
    """
    Represents a single tariff rate change with its associated risk level.

    Attributes:
        category: The category or classification of the tariff item.
        old_rate: The original tariff rate before the change.
        new_rate: The new tariff rate after the change.
        delta_pct: The percentage change between old and new rates.
        risk_level: The assessed risk level (LOW, MEDIUM, or HIGH).
        note: Additional notes or context about the change.
    """
    category: str = Field(description="Category or classification of the tariff item")
    old_rate: float = Field(description="Original tariff rate")
    new_rate: float = Field(description="New tariff rate")
    delta_pct: float = Field(description="Percentage change between rates")
    risk_level: RiskLevel = Field(default="LOW", description="Assessed risk level")
    note: str = Field(default="", description="Additional notes or context")


class RiskAgentInput(BaseModel):
    """
    Input schema for the Risk Agent.

    Attributes:
        partner_name: Name of the partner organization.
        confidence: Confidence score from the verification process (0-100).
        comparison_rows: List of rate changes to assess for risk.
    """
    partner_name: str = Field(description="Name of the partner organization")
    confidence: int = Field(ge=0, le=100, description="Confidence score from verification (0-100)")
    comparison_rows: list[RiskItem] = Field(description="List of rate changes to assess")


class RiskSummary(BaseModel):
    """
    Summary of risk assessment for tariff changes.

    Attributes:
        partner_name: Name of the partner organization.
        total_rows: Total number of tariff rows analyzed.
        changed_rows: Number of rows with rate changes.
        flagged_rows: Number of rows with MEDIUM or HIGH risk.
        highest_risk: The highest risk level found across all changes.
        recommendation: Action recommendation based on risk assessment.
        items: Full list of assessed risk items.
    """
    partner_name: str = Field(description="Name of the partner organization")
    total_rows: int = Field(description="Total number of tariff rows analyzed")
    changed_rows: int = Field(description="Number of rows with rate changes")
    flagged_rows: int = Field(description="Number of rows with MEDIUM or HIGH risk")
    highest_risk: RiskLevel = Field(description="Highest risk level found")
    recommendation: str = Field(description="Action recommendation based on assessment")
    items: list[RiskItem] = Field(default_factory=list, description="Full list of assessed risk items")


class RiskAgent:
    """
    Agent responsible for assessing risk levels of tariff changes.

    This agent analyzes rate changes and determines the overall risk level,
    providing recommendations on whether changes require additional approval
    or can proceed safely.
    """

    def assess(self, payload: RiskAgentInput) -> RiskSummary:
        """
        Assess the risk level of tariff rate changes.

        This method analyzes the comparison rows to determine:
        - Total number of rows analyzed
        - Number of rows with actual changes
        - Number of rows flagged as MEDIUM or HIGH risk
        - Highest risk level across all changes
        - Appropriate recommendation based on risk and confidence

        Args:
            payload: Input containing partner name, confidence score, and rate changes.

        Returns:
            RiskSummary: Comprehensive risk assessment with statistics and recommendations.
        """
        # Calculate basic statistics
        total_rows = len(payload.comparison_rows)
        changed_rows = sum(
            1 for row in payload.comparison_rows if row.old_rate != row.new_rate
        )
        flagged_rows = sum(
            1 for row in payload.comparison_rows if row.risk_level != "LOW"
        )

        # Determine the highest risk level present
        if any(row.risk_level == "HIGH" for row in payload.comparison_rows):
            highest_risk: RiskLevel = "HIGH"
        elif any(row.risk_level == "MEDIUM" for row in payload.comparison_rows):
            highest_risk = "MEDIUM"
        else:
            highest_risk = "LOW"

        # Generate recommendation based on risk and confidence
        # High risk or low confidence requires manager approval
        if payload.confidence < 90 or highest_risk == "HIGH":
            recommendation = "Manager approval required"
        # Any flagged items warrant review
        elif flagged_rows > 0:
            recommendation = "Review recommended before approval"
        # Safe to proceed if no issues
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
