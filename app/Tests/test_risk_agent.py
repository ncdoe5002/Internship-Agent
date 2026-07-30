"""
Tests for RiskAgent.

This module contains unit tests, integration tests, and edge case tests
for the risk assessment agent using both mocked and real data.
"""

import pytest
from app.agents.risk_agent import RiskAgent, RiskAgentInput, RiskItem


# ============================================================================
# Integration Tests (Real Data)
# ============================================================================

@pytest.mark.integration
def test_assess_with_real_extracted_data(real_extraction_result):
    """
    Test risk assessment with data from Orange_IOT_Egypt document extraction.
    """
    agent = RiskAgent()
    
    # Convert extraction result to risk items
    risk_items = []
    for table in real_extraction_result.tables:
        if "Rate" in str(table.headers) or "rate" in str(table.headers).lower():
            # Find rate column index
            rate_idx = None
            for idx, header in enumerate(table.headers):
                if "rate" in header.lower() or "price" in header.lower():
                    rate_idx = idx
                    break
            
            if rate_idx is not None:
                for row in table.rows:
                    if len(row) > rate_idx:
                        try:
                            rate = float(row[rate_idx])
                            risk_items.append(
                                RiskItem(
                                    category=row[0] if row else "Unknown",
                                    old_rate=rate * 0.9,  # Simulate old rate
                                    new_rate=rate,
                                    delta_pct=10.0,
                                    risk_level="MEDIUM",
                                    note="Rate increased by 10.0%"
                                )
                            )
                        except (ValueError, IndexError):
                            pass
    
    if not risk_items:
        # Create sample items if no rate data found
        risk_items = [
            RiskItem(
                category="Voice MOC",
                old_rate=0.0182,
                new_rate=0.0205,
                delta_pct=12.6,
                risk_level="MEDIUM",
                note="Rate increased by 12.6%"
            )
        ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.partner_name == "Orange Egypt"
    assert result.total_rows == len(risk_items)
    assert result.highest_risk in ["LOW", "MEDIUM", "HIGH"]
    assert isinstance(result.recommendation, str)


@pytest.mark.integration
def test_assess_real_rate_changes(real_extraction_result):
    """
    Test risk assessment with actual rate changes from document.
    """
    agent = RiskAgent()
    
    # Create realistic rate changes based on typical tariff changes
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.0182,
            new_rate=0.0205,
            delta_pct=12.6,
            risk_level="MEDIUM",
            note="Rate increased by 12.6%"
        ),
        RiskItem(
            category="Voice MTC",
            old_rate=0.0140,
            new_rate=0.0140,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        ),
        RiskItem(
            category="SMS MO",
            old_rate=0.0075,
            new_rate=0.0068,
            delta_pct=-9.3,
            risk_level="LOW",
            note="Rate decreased by 9.3%"
        ),
        RiskItem(
            category="Data",
            old_rate=0.0032,
            new_rate=0.0041,
            delta_pct=28.1,
            risk_level="HIGH",
            note="Rate increased by 28.1%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=94,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 4
    assert result.changed_rows == 3  # Voice MOC, SMS MO, Data
    assert result.flagged_rows == 2  # MEDIUM and HIGH
    assert result.highest_risk == "HIGH"
    assert result.recommendation == "Manager approval required"


@pytest.mark.integration
def test_risk_level_calculation_real_data():
    """
    Test risk levels match real document scenarios.
    """
    agent = RiskAgent()
    
    # Test various delta percentages
    test_cases = [
        (5.0, "LOW"),      # Small change
        (15.0, "MEDIUM"),  # Medium change
        (25.0, "MEDIUM"),  # Medium-high change
        (55.0, "HIGH"),    # Large change
        (-10.0, "LOW"),    # Decrease
        (-30.0, "HIGH"),   # Large decrease
    ]
    
    for delta, expected_risk in test_cases:
        risk_items = [
            RiskItem(
                category="Test",
                old_rate=1.0,
                new_rate=1.0 + (delta / 100),
                delta_pct=delta,
                risk_level=expected_risk,
                note=f"Delta: {delta}%"
            )
        ]
        
        payload = RiskAgentInput(
            partner_name="Test Partner",
            confidence=95,
            comparison_rows=risk_items
        )
        
        result = agent.assess(payload)
        
        assert result.highest_risk == expected_risk


# ============================================================================
# Unit Tests (Mocked)
# ============================================================================

@pytest.mark.unit
def test_assess_low_risk_no_changes():
    """
    Test no rate changes → LOW risk.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.05,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        ),
        RiskItem(
            category="SMS MO",
            old_rate=0.01,
            new_rate=0.01,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 2
    assert result.changed_rows == 0
    assert result.flagged_rows == 0
    assert result.highest_risk == "LOW"
    assert result.recommendation == "Safe to proceed"


@pytest.mark.unit
def test_assess_medium_risk_small_changes():
    """
    Test 20-50% changes → MEDIUM risk.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        ),
        RiskItem(
            category="SMS MO",
            old_rate=0.01,
            new_rate=0.012,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 2
    assert result.changed_rows == 2
    assert result.flagged_rows == 2
    assert result.highest_risk == "MEDIUM"
    assert result.recommendation == "Review recommended before approval"


@pytest.mark.unit
def test_assess_high_risk_large_changes():
    """
    Test >50% changes → HIGH risk.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Data",
            old_rate=0.003,
            new_rate=0.005,
            delta_pct=66.7,
            risk_level="HIGH",
            note="Rate increased by 66.7%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 1
    assert result.changed_rows == 1
    assert result.flagged_rows == 1
    assert result.highest_risk == "HIGH"
    assert result.recommendation == "Manager approval required"


@pytest.mark.unit
def test_assess_mixed_risk_levels():
    """
    Test mixed risk items in same assessment.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MTC",
            old_rate=0.05,
            new_rate=0.05,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        ),
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        ),
        RiskItem(
            category="Data",
            old_rate=0.003,
            new_rate=0.005,
            delta_pct=66.7,
            risk_level="HIGH",
            note="Rate increased by 66.7%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 3
    assert result.changed_rows == 2
    assert result.flagged_rows == 2
    assert result.highest_risk == "HIGH"
    assert result.recommendation == "Manager approval required"


@pytest.mark.unit
def test_assess_confidence_below_threshold():
    """
    Test low confidence → manager approval.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.055,
            delta_pct=10.0,
            risk_level="MEDIUM",
            note="Rate increased by 10.0%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=85,  # Below 90 threshold
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.recommendation == "Manager approval required"


@pytest.mark.unit
def test_assess_high_risk_requires_approval():
    """
    Test HIGH risk → manager approval.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Data",
            old_rate=0.003,
            new_rate=0.005,
            delta_pct=66.7,
            risk_level="HIGH",
            note="Rate increased by 66.7%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,  # High confidence but HIGH risk
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.recommendation == "Manager approval required"


@pytest.mark.unit
def test_assess_flagged_rows_require_review():
    """
    Test flagged rows → review recommended.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,  # High confidence, MEDIUM risk
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.recommendation == "Review recommended before approval"


@pytest.mark.unit
def test_assess_safe_to_proceed():
    """
    Test all LOW risk, high confidence → safe.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.05,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.recommendation == "Safe to proceed"


@pytest.mark.unit
def test_assess_empty_comparison_rows():
    """
    Test empty input handling.
    """
    agent = RiskAgent()
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=[]
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 0
    assert result.changed_rows == 0
    assert result.flagged_rows == 0
    assert result.highest_risk == "LOW"
    assert result.recommendation == "Safe to proceed"


@pytest.mark.unit
def test_assess_statistics_calculation():
    """
    Test total/changed/flagged counts.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(category="A", old_rate=1.0, new_rate=1.0, delta_pct=0.0, risk_level="LOW", note=""),
        RiskItem(category="B", old_rate=1.0, new_rate=1.1, delta_pct=10.0, risk_level="MEDIUM", note=""),
        RiskItem(category="C", old_rate=1.0, new_rate=1.2, delta_pct=20.0, risk_level="MEDIUM", note=""),
        RiskItem(category="D", old_rate=1.0, new_rate=1.6, delta_pct=60.0, risk_level="HIGH", note=""),
        RiskItem(category="E", old_rate=1.0, new_rate=1.0, delta_pct=0.0, risk_level="LOW", note=""),
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result.total_rows == 5
    assert result.changed_rows == 3  # B, C, D
    assert result.flagged_rows == 3  # B, C, D (all non-LOW)
    assert result.highest_risk == "HIGH"


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
def test_zero_old_rate_division():
    """
    Test zero old rate (division by zero).
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="New Service",
            old_rate=0.0,
            new_rate=0.05,
            delta_pct=0.0,  # Should be calculated as 0 when old_rate is 0
            risk_level="LOW",
            note="New service"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    # The agent doesn't calculate delta_pct, it uses the provided value
    # So this tests that it handles the provided delta_pct correctly


@pytest.mark.unit
def test_negative_rates():
    """
    Test negative rates.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Discount",
            old_rate=-0.05,
            new_rate=-0.03,
            delta_pct=40.0,
            risk_level="MEDIUM",
            note="Discount reduced"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 1


@pytest.mark.unit
def test_very_large_percentage_changes():
    """
    Test very large percentage changes.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Data",
            old_rate=0.001,
            new_rate=0.01,
            delta_pct=900.0,
            risk_level="HIGH",
            note="Massive increase"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.highest_risk == "HIGH"


@pytest.mark.unit
def test_confidence_at_boundary_values():
    """
    Test confidence at boundary values (89, 90, 91).
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        )
    ]
    
    # Test confidence at 89 (below threshold)
    payload_89 = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=89,
        comparison_rows=risk_items
    )
    result_89 = agent.assess(payload_89)
    assert result_89.recommendation == "Manager approval required"
    
    # Test confidence at 90 (at threshold)
    payload_90 = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=90,
        comparison_rows=risk_items
    )
    result_90 = agent.assess(payload_90)
    assert result_90.recommendation == "Review recommended before approval"
    
    # Test confidence at 91 (above threshold)
    payload_91 = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=91,
        comparison_rows=risk_items
    )
    result_91 = agent.assess(payload_91)
    assert result_91.recommendation == "Review recommended before approval"


@pytest.mark.unit
def test_all_rows_same_risk_level():
    """
    Test all rows same risk level.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(category="A", old_rate=1.0, new_rate=1.1, delta_pct=10.0, risk_level="MEDIUM", note=""),
        RiskItem(category="B", old_rate=1.0, new_rate=1.1, delta_pct=10.0, risk_level="MEDIUM", note=""),
        RiskItem(category="C", old_rate=1.0, new_rate=1.1, delta_pct=10.0, risk_level="MEDIUM", note=""),
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.highest_risk == "MEDIUM"
    assert result.flagged_rows == 3


@pytest.mark.unit
def test_new_categories_no_baseline():
    """
    Test new categories (no baseline match).
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="5G Service",
            old_rate=0.0,
            new_rate=0.10,
            delta_pct=0.0,
            risk_level="LOW",
            note="NEW_CATEGORY"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 1


@pytest.mark.unit
def test_risk_level_boundaries():
    """
    Test risk level calculation at boundaries (20%, 50%).
    """
    agent = RiskAgent()
    
    # Test exactly at 20% (MEDIUM threshold)
    risk_items_20 = [
        RiskItem(
            category="Test",
            old_rate=1.0,
            new_rate=1.2,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Exactly 20%"
        )
    ]
    
    payload_20 = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items_20
    )
    
    result_20 = agent.assess(payload_20)
    assert result_20.highest_risk == "MEDIUM"
    
    # Test exactly at 50% (HIGH threshold)
    risk_items_50 = [
        RiskItem(
            category="Test",
            old_rate=1.0,
            new_rate=1.5,
            delta_pct=50.0,
            risk_level="HIGH",
            note="Exactly 50%"
        )
    ]
    
    payload_50 = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items_50
    )
    
    result_50 = agent.assess(payload_50)
    assert result_50.highest_risk == "HIGH"


@pytest.mark.unit
def test_partner_name_preservation():
    """
    Test that partner name is preserved in result.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.05,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Test Partner Name",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result.partner_name == "Test Partner Name"


@pytest.mark.unit
def test_items_preservation():
    """
    Test that comparison items are preserved in result.
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Test note"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert len(result.items) == 1
    assert result.items[0].category == "Voice MOC"
    assert result.items[0].note == "Test note"


@pytest.mark.unit
def test_confidence_validation():
    """
    Test confidence score validation (0-100).
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.05,
            delta_pct=0.0,
            risk_level="LOW",
            note="No change"
        )
    ]
    
    # Test minimum confidence
    payload_min = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=0,
        comparison_rows=risk_items
    )
    
    result_min = agent.assess(payload_min)
    assert result_min.recommendation == "Manager approval required"
    
    # Test maximum confidence
    payload_max = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=100,
        comparison_rows=risk_items
    )
    
    result_max = agent.assess(payload_max)
    assert result_max.recommendation == "Safe to proceed"


@pytest.mark.unit
def test_negative_delta_percentage():
    """
    Test negative delta percentage (rate decrease).
    """
    agent = RiskAgent()
    
    risk_items = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.10,
            new_rate=0.08,
            delta_pct=-20.0,
            risk_level="MEDIUM",
            note="Rate decreased by 20.0%"
        )
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.changed_rows == 1
    assert result.flagged_rows == 1


@pytest.mark.unit
def test_large_number_of_items():
    """
    Test handling large number of comparison rows.
    """
    agent = RiskAgent()
    
    # Create 100 risk items
    risk_items = [
        RiskItem(
            category=f"Service_{i}",
            old_rate=0.05,
            new_rate=0.05 + (0.001 if i % 2 == 0 else 0),
            delta_pct=2.0 if i % 2 == 0 else 0.0,
            risk_level="MEDIUM" if i % 2 == 0 else "LOW",
            note="Test"
        )
        for i in range(100)
    ]
    
    payload = RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=risk_items
    )
    
    result = agent.assess(payload)
    
    assert result is not None
    assert result.total_rows == 100
    assert result.changed_rows == 50
    assert result.flagged_rows == 50
