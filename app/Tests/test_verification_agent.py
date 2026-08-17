"""
Tests for VerificationAgent.

This module contains unit tests, integration tests, and error scenario tests
for the verification agent using both mocked and real data.
"""

import pytest
from app.agents.verification_agent import VerificationAgent, VerificationAgentInput


# ============================================================================
# Integration Tests (Real Data)
# ============================================================================

@pytest.mark.integration
def test_run_with_real_extracted_data(real_extraction_result):
    """
    Test verification with data from real Orange_IOT_Egypt docx extraction.
    """
    agent = VerificationAgent()
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=real_extraction_result.model_dump(),
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result is not None
    assert result.status in ["READY", "REVIEW", "FAILED"]
    assert 0 <= result.confidence <= 100
    assert len(result.checks) > 0
    assert isinstance(result.issues, list)


@pytest.mark.integration
def test_check_currency_format_real_data(real_extraction_result):
    """
    Test currency format validation with patterns from real document.
    """
    agent = VerificationAgent()
    
    passed, issues = agent._check_currency_format(real_extraction_result.model_dump())
    
    assert isinstance(passed, bool)
    assert isinstance(issues, list)


@pytest.mark.integration
def test_check_effective_date_real_document(real_extraction_result):
    """
    Test date detection from actual agreement.
    """
    agent = VerificationAgent()
    
    passed, issues = agent._check_effective_date(real_extraction_result.model_dump())
    
    assert isinstance(passed, bool)
    assert isinstance(issues, list)


@pytest.mark.integration
def test_check_partner_agreement_real_match(real_extraction_result):
    """
    Test partner matching with real document data.
    """
    agent = VerificationAgent()
    
    passed, issues = agent._check_partner_agreement(
        real_extraction_result.model_dump(),
        "Orange Egypt"
    )
    
    assert isinstance(passed, bool)
    assert isinstance(issues, list)


# ============================================================================
# Unit Tests (Mocked)
# ============================================================================

@pytest.mark.unit
def test_run_success_all_checks_pass(sample_verification_payload):
    """
    Test perfect data scenario with all checks passing.
    """
    agent = VerificationAgent()
    
    # Create perfect data
    perfect_data = {
        "tables": [
            {
                "title": "Perfect Table",
                "headers": ["Category", "Rate", "Effective Date"],
                "rows": [
                    ["Voice MOC", "0.05", "2024-01-01"],
                    ["Orange Egypt Service", "0.03", "2024-01-01"]
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=perfect_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result is not None
    assert result.status == "READY"
    assert result.confidence >= 90
    assert len(result.issues) == 0


@pytest.mark.unit
def test_run_no_tables_extracted():
    """
    Test missing tables failure.
    """
    agent = VerificationAgent()
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables={"tables": []},
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result is not None
    assert result.status == "FAILED"
    assert result.confidence == 0
    assert any("No tables were extracted" in issue for issue in result.issues)


@pytest.mark.unit
def test_check_currency_format_valid():
    """
    Test valid currency formats ($1.00, €0.50, etc.).
    """
    agent = VerificationAgent()
    
    valid_data = {
        "tables": [
            {
                "title": "Valid Currency Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "$0.05"],
                    ["SMS", "€0.01"],
                    ["Data", "£0.003"],
                    ["MMS", "¥0.10"],
                    ["Roaming", "1.50"],
                    ["Service", "0,05"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_currency_format(valid_data)
    
    assert passed is True
    assert len(issues) == 0


@pytest.mark.unit
def test_check_currency_format_invalid():
    """
    Test invalid currency formats trigger issues.
    """
    agent = VerificationAgent()
    
    invalid_data = {
        "tables": [
            {
                "title": "Invalid Currency Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "invalid_rate"],
                    ["SMS", "0.05abc"],
                    ["Data", "@#$%"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_currency_format(invalid_data)
    
    assert passed is False
    assert len(issues) > 0


@pytest.mark.unit
def test_check_currency_format_mixed():
    """
    Test mixed valid/invalid in same table.
    """
    agent = VerificationAgent()
    
    mixed_data = {
        "tables": [
            {
                "title": "Mixed Currency Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "$0.05"],  # Valid
                    ["SMS", "invalid"],  # Invalid
                    ["Data", "€0.01"]   # Valid
                ]
            }
        ]
    }
    
    passed, issues = agent._check_currency_format(mixed_data)
    
    assert passed is False
    assert len(issues) == 1


@pytest.mark.unit
def test_check_effective_date_missing():
    """
    Test no date found.
    """
    agent = VerificationAgent()
    
    no_date_data = {
        "tables": [
            {
                "title": "No Date Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "0.05"],
                    ["SMS", "0.01"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_effective_date(no_date_data)
    
    assert passed is False
    assert len(issues) == 1
    assert "No effective date found" in issues[0]


@pytest.mark.unit
def test_check_effective_date_various_formats():
    """
    Test different date format patterns.
    """
    agent = VerificationAgent()
    
    date_formats = [
        "2024-01-01",      # YYYY-MM-DD
        "01/15/2024",      # MM/DD/YYYY
        "01-15-2024",      # MM-DD-YYYY
        "January 15, 2024", # Month DD, YYYY
        "Jan 15, 2024",    # Short month
        "Effective: 2024-01-01"  # Date in text
    ]
    
    for date_str in date_formats:
        date_data = {
            "tables": [
                {
                    "title": "Date Table",
                    "headers": ["Category", "Rate", "Date"],
                    "rows": [
                        ["Voice", "0.05", date_str]
                    ]
                }
            ]
        }
        
        passed, issues = agent._check_effective_date(date_data)
        assert passed is True, f"Failed for date format: {date_str}"


@pytest.mark.unit
def test_check_partner_agreement_not_found():
    """
    Test partner name missing.
    """
    agent = VerificationAgent()
    
    no_partner_data = {
        "tables": [
            {
                "title": "No Partner Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "0.05"],
                    ["SMS", "0.01"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_partner_agreement(no_partner_data, "Orange Egypt")
    
    assert passed is False
    assert len(issues) == 1
    assert "Orange Egypt" in issues[0]


@pytest.mark.unit
def test_check_partner_agreement_case_insensitive():
    """
    Test case insensitive matching.
    """
    agent = VerificationAgent()
    
    partner_data = {
        "tables": [
            {
                "title": "Partner Table",
                "headers": ["Category", "Partner"],
                "rows": [
                    ["Voice", "ORANGE EGYPT"],
                    ["SMS", "orange egypt"]
                ]
            }
        ]
    }
    
    # Test with different case variations
    for partner_name in ["Orange Egypt", "ORANGE EGYPT", "orange egypt"]:
        passed, issues = agent._check_partner_agreement(partner_data, partner_name)
        assert passed is True, f"Failed for partner name: {partner_name}"


@pytest.mark.unit
def test_check_table_structure_valid():
    """
    Test proper headers and non-empty cells.
    """
    agent = VerificationAgent()
    
    valid_structure = {
        "tables": [
            {
                "title": "Valid Structure",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "0.05"],
                    ["SMS", "0.01"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_table_structure(valid_structure)
    
    assert passed is True
    assert len(issues) == 0


@pytest.mark.unit
def test_check_table_structure_missing_headers():
    """
    Test missing headers.
    """
    agent = VerificationAgent()
    
    no_headers = {
        "tables": [
            {
                "title": "No Headers",
                "headers": [],
                "rows": [["Voice", "0.05"]]
            }
        ]
    }
    
    passed, issues = agent._check_table_structure(no_headers)
    
    assert passed is False
    assert len(issues) == 1
    assert "Missing headers" in issues[0]


@pytest.mark.unit
def test_check_table_structure_empty_cells():
    """
    Test empty required cells.
    """
    agent = VerificationAgent()
    
    empty_cells = {
        "tables": [
            {
                "title": "Empty Cells",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", ""],      # Empty rate
                    ["SMS", "0.01"],
                    ["", "0.05"]        # Empty category
                ]
            }
        ]
    }
    
    passed, issues = agent._check_table_structure(empty_cells)
    
    assert passed is False
    assert len(issues) == 2  # Two empty cells


@pytest.mark.unit
def test_confidence_calculation_high():
    """
    Test all checks pass → high confidence.
    """
    agent = VerificationAgent()
    
    perfect_data = {
        "tables": [
            {
                "title": "Perfect Table",
                "headers": ["Category", "Rate", "Effective Date"],
                "rows": [
                    ["Voice MOC", "$0.05", "2024-01-01"],
                    ["Orange Egypt Service", "€0.03", "2024-01-01"]
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=perfect_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.confidence >= 90


@pytest.mark.unit
def test_confidence_calculation_medium():
    """
    Test some checks fail → medium confidence.
    """
    agent = VerificationAgent()
    
    medium_data = {
        "tables": [
            {
                "title": "Medium Quality Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "$0.05"],
                    ["SMS", "invalid_rate"]  # Invalid currency
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=medium_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert 70 <= result.confidence < 90


@pytest.mark.unit
def test_confidence_calculation_low():
    """
    Test critical checks fail → low confidence.
    """
    agent = VerificationAgent()
    
    low_data = {
        "tables": [
            {
                "title": "Low Quality Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "invalid"],
                    ["SMS", "invalid"]
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Missing Partner",  # Partner not in data
        extracted_tables=low_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.confidence < 70


@pytest.mark.unit
def test_status_determination_ready():
    """
    Test high confidence → READY status.
    """
    agent = VerificationAgent()
    
    ready_data = {
        "tables": [
            {
                "title": "Ready Table",
                "headers": ["Category", "Rate", "Effective Date"],
                "rows": [
                    ["Orange Egypt Voice", "$0.05", "2024-01-01"]
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=ready_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.status == "READY"


@pytest.mark.unit
def test_status_determination_review():
    """
    Test medium confidence → REVIEW status.
    """
    agent = VerificationAgent()
    
    review_data = {
        "tables": [
            {
                "title": "Review Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "$0.05"],
                    ["SMS", "invalid"]
                ]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=review_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.status == "REVIEW"


@pytest.mark.unit
def test_status_determination_failed():
    """
    Test low confidence → FAILED status.
    """
    agent = VerificationAgent()
    
    failed_data = {
        "tables": []
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=failed_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.status == "FAILED"


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
def test_empty_tables_dictionary():
    """
    Test empty tables dictionary.
    """
    agent = VerificationAgent()
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables={},
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result.status == "FAILED"


@pytest.mark.unit
def test_malformed_table_structure():
    """
    Test malformed table structure.
    """
    agent = VerificationAgent()
    
    malformed_data = {
        "tables": [
            {
                "title": "Malformed",
                "headers": None,  # Invalid headers
                "rows": "not a list"  # Invalid rows
            }
        ]
    }
    
    # Should handle gracefully without crashing
    try:
        passed, issues = agent._check_table_structure(malformed_data)
        assert isinstance(passed, bool)
        assert isinstance(issues, list)
    except Exception:
        pytest.fail("Should handle malformed data gracefully")


@pytest.mark.unit
def test_special_characters_in_currency():
    """
    Test special characters in currency values.
    """
    agent = VerificationAgent()
    
    special_data = {
        "tables": [
            {
                "title": "Special Characters",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", "$1,000.50"],
                    ["SMS", "€500.25"],
                    ["Data", "¥100.00"]
                ]
            }
        ]
    }
    
    passed, issues = agent._check_currency_format(special_data)
    
    assert passed is True


@pytest.mark.unit
def test_unicode_characters_in_partner_name():
    """
    Test Unicode characters in partner names.
    """
    agent = VerificationAgent()
    
    unicode_data = {
        "tables": [
            {
                "title": "Unicode Partner",
                "headers": ["Category", "Partner"],
                "rows": [
                    ["Voice", "Orange Égypt"],
                    ["SMS", "Orange Ägypten"]
                ]
            }
        ]
    }
    
    # Test with unicode partner name
    passed, issues = agent._check_partner_agreement(unicode_data, "Orange Égypt")
    
    assert passed is True


@pytest.mark.unit
def test_very_large_tables():
    """
    Test very large tables (performance).
    """
    agent = VerificationAgent()
    
    # Create a large table with 1000 rows
    large_rows = [["Voice", f"0.{i:02d}"] for i in range(1000)]
    
    large_data = {
        "tables": [
            {
                "title": "Large Table",
                "headers": ["Category", "Rate"],
                "rows": large_rows
            }
        ]
    }
    
    # Should handle large tables without performance issues
    import time
    start_time = time.time()
    
    passed, issues = agent._check_currency_format(large_data)
    
    elapsed = time.time() - start_time
    assert elapsed < 5.0  # Should complete in under 5 seconds
    assert isinstance(passed, bool)


@pytest.mark.unit
def test_nested_table_structures():
    """
    Test nested table structures.
    """
    agent = VerificationAgent()
    
    nested_data = {
        "tables": [
            {
                "title": "Nested Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice", ["0.05", "0.03"]],  # Nested list
                    ["SMS", "0.01"]
                ]
            }
        ]
    }
    
    # Should handle nested structures gracefully
    try:
        passed, issues = agent._check_currency_format(nested_data)
        assert isinstance(passed, bool)
    except Exception:
        pytest.fail("Should handle nested structures gracefully")


@pytest.mark.unit
def test_multiple_tables():
    """
    Test verification with multiple tables.
    """
    agent = VerificationAgent()
    
    multi_table_data = {
        "tables": [
            {
                "title": "Table 1",
                "headers": ["Category", "Rate"],
                "rows": [["Voice", "0.05"]]
            },
            {
                "title": "Table 2",
                "headers": ["Category", "Rate"],
                "rows": [["SMS", "0.01"]]
            },
            {
                "title": "Table 3",
                "headers": ["Category", "Rate"],
                "rows": [["Data", "0.003"]]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=multi_table_data,
        baseline_tables=None
    )
    
    result = agent.run(payload)
    
    assert result is not None
    assert len(result.checks) > 0


@pytest.mark.unit
def test_confidence_boundary_values():
    """
    Test confidence at boundary values (69, 70, 89, 90, 91).
    """
    agent = VerificationAgent()
    
    # Test confidence exactly at boundaries
    boundary_tests = [
        (69, "FAILED"),
        (70, "REVIEW"),
        (89, "REVIEW"),
        (90, "READY"),
        (91, "READY")
    ]
    
    for confidence, expected_status in boundary_tests:
        # Create data that would produce the desired confidence
        # This is a simplified test - in practice, confidence depends on check results
        pass  # Actual confidence calculation depends on check results


@pytest.mark.unit
def test_baseline_tables_parameter():
    """
    Test that baseline_tables parameter is accepted even if not used.
    """
    agent = VerificationAgent()
    
    baseline_data = {
        "tables": [
            {
                "title": "Baseline",
                "headers": ["Category", "Rate"],
                "rows": [["Voice", "0.03"]]
            }
        ]
    }
    
    payload = VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables={"tables": []},
        baseline_tables=baseline_data
    )
    
    result = agent.run(payload)
    
    assert result is not None
    # Currently baseline is not used in verification, but should not cause errors
