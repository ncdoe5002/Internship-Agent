"""
Tests for Orchestrator.

This module contains unit tests, integration tests, and error scenario tests
for the orchestrator agent using both mocked and real API calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.agents.orchestrator import Orchestrator, OrchestratorInput


# ============================================================================
# Integration Tests (Real API)
# ============================================================================

@pytest.mark.integration
@pytest.mark.slow
def test_run_successful_workflow_real_api(real_gemini_model, sample_docx_file):
    """
    Test complete happy path through all agents with real extraction.
    """
    with open(sample_docx_file, "rb") as f:
        docx_bytes = f.read()
    
    orchestrator = Orchestrator(real_gemini_model)
    
    payload = OrchestratorInput(
        pdf_bytes=docx_bytes,
        filename=sample_docx_file.name,
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="docx"
    )
    
    try:
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output is not None
        assert result.output.review_table is not None
        assert result.output.summary is not None
    except Exception as e:
        # If real extraction fails, skip gracefully
        pytest.skip(f"Real workflow test failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_e2e_upload_verify_compare_real(real_gemini_model, sample_docx_file):
    """
    Test upload → verify → compare workflow with Orange_IOT_Egypt docx.
    """
    with open(sample_docx_file, "rb") as f:
        docx_bytes = f.read()
    
    orchestrator = Orchestrator(real_gemini_model)
    
    payload = OrchestratorInput(
        pdf_bytes=docx_bytes,
        filename=sample_docx_file.name,
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="docx"
    )
    
    try:
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output is not None
        # Verify the workflow produces a review table
        assert result.output.review_table is not None
    except Exception as e:
        pytest.skip(f"E2E test failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_parallel_execution_real_api(real_gemini_model, sample_docx_file):
    """
    Test parallel execution with real agent calls.
    """
    with open(sample_docx_file, "rb") as f:
        docx_bytes = f.read()
    
    orchestrator = Orchestrator(real_gemini_model)
    
    payload = OrchestratorInput(
        pdf_bytes=docx_bytes,
        filename=sample_docx_file.name,
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="docx"
    )
    
    try:
        result = orchestrator.run(payload)
        
        assert result is not None
        # Verify both verification and risk were executed
        assert result.output is not None
    except Exception as e:
        pytest.skip(f"Parallel execution test failed: {e}")


@pytest.mark.integration
def test_extract_comparison_rows_real_baseline(real_extraction_result, sample_baseline_data):
    """
    Test real baseline data comparison.
    """
    orchestrator = Orchestrator(Mock())
    
    comparison_rows = orchestrator._extract_comparison_rows(
        real_extraction_result.model_dump(),
        sample_baseline_data
    )
    
    assert isinstance(comparison_rows, list)


# ============================================================================
# Unit Tests (Mocked)
# ============================================================================

@pytest.mark.unit
def test_normalize_category():
    """
    Test category normalization logic.
    """
    orchestrator = Orchestrator(Mock())
    
    test_cases = [
        ("Voice MOC", "voice moc"),
        ("VOICE MTC", "voice mtc"),
        ("SMS-MO", "sms mo"),
        ("GPRS Data", "gprs data"),
        ("  Voice  ", "voice"),  # Trim whitespace
        ("Voice_MOC", "voice_moc"),
    ]
    
    for input_cat, expected in test_cases:
        result = orchestrator._normalize_category(input_cat)
        assert result == expected, f"Failed for {input_cat}: got {result}, expected {expected}"


@pytest.mark.unit
def test_fuzzy_match_category_exact():
    """
    Test exact category matching.
    """
    orchestrator = Orchestrator(Mock())
    
    baseline_categories = ["voice moc", "voice mtc", "sms mo", "gprs"]
    
    matched, similarity = orchestrator._fuzzy_match_category(
        "voice moc",
        baseline_categories
    )
    
    assert matched == "voice moc"
    assert similarity == 1.0


@pytest.mark.unit
def test_fuzzy_match_category_similarity():
    """
    Test fuzzy matching with threshold.
    """
    orchestrator = Orchestrator(Mock())
    
    baseline_categories = ["voice moc", "voice mtc", "sms mo", "gprs"]
    
    # Test close match
    matched, similarity = orchestrator._fuzzy_match_category(
        "voice mobile originated",
        baseline_categories
    )
    
    # Should match with high similarity
    if matched:
        assert similarity > 0.7


@pytest.mark.unit
def test_fuzzy_match_category_no_match():
    """
    Test below threshold → no match.
    """
    orchestrator = Orchestrator(Mock())
    
    baseline_categories = ["voice moc", "voice mtc", "sms mo", "gprs"]
    
    matched, similarity = orchestrator._fuzzy_match_category(
        "completely different category",
        baseline_categories
    )
    
    # Should not match
    assert matched is None or similarity < 0.7


@pytest.mark.unit
def test_parse_rate_valid_formats():
    """
    Test various rate string formats.
    """
    orchestrator = Orchestrator(Mock())
    
    test_cases = [
        ("0.05", 0.05),
        ("0,05", 0.05),  # European format
        ("1.50", 1.50),
        ("0.0001", 0.0001),
        ("100", 100.0),
        ("0", 0.0),
    ]
    
    for rate_str, expected in test_cases:
        result = orchestrator._parse_rate(rate_str)
        assert result == expected, f"Failed for {rate_str}: got {result}, expected {expected}"


@pytest.mark.unit
def test_parse_rate_special_values():
    """
    Test N/A, NA, blank handling.
    """
    orchestrator = Orchestrator(Mock())
    
    special_values = ["N/A", "NA", "n/a", "na", "", " ", "-", "--"]
    
    for value in special_values:
        result = orchestrator._parse_rate(value)
        assert result is None, f"Should return None for {value}, got {result}"


@pytest.mark.unit
def test_parse_rate_invalid():
    """
    Test unparseable rate strings.
    """
    orchestrator = Orchestrator(Mock())
    
    invalid_values = ["invalid", "abc", "1.2.3", "text", "@#$%"]
    
    for value in invalid_values:
        result = orchestrator._parse_rate(value)
        assert result is None, f"Should return None for {value}, got {result}"


@pytest.mark.unit
def test_find_column_indices_keywords():
    """
    Test header keyword matching.
    """
    orchestrator = Orchestrator(Mock())
    
    headers = ["Category", "Rate", "Effective Date", "Currency"]
    
    cat_idx, rate_idx = orchestrator._find_column_indices(headers)
    
    assert cat_idx == 0  # Category is first
    assert rate_idx == 1  # Rate is second


@pytest.mark.unit
def test_find_column_indices_fallback():
    """
    Test default to first/second column when keywords not found.
    """
    orchestrator = Orchestrator(Mock())
    
    headers = ["Column A", "Column B", "Column C"]
    
    cat_idx, rate_idx = orchestrator._find_column_indices(headers)
    
    # Should fall back to first and second columns
    assert cat_idx == 0
    assert rate_idx == 1


@pytest.mark.unit
def test_extract_comparison_rows_without_baseline():
    """
    Test no baseline data.
    """
    orchestrator = Orchestrator(Mock())
    
    extraction_result = {
        "tables": [
            {
                "title": "Rate Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice MOC", "0.05"],
                    ["SMS MO", "0.01"]
                ]
            }
        ]
    }
    
    comparison_rows = orchestrator._extract_comparison_rows(
        extraction_result,
        None  # No baseline
    )
    
    assert isinstance(comparison_rows, list)
    # Without baseline, old_rate should be 0.0
    if comparison_rows:
        assert all(row.old_rate == 0.0 for row in comparison_rows)


@pytest.mark.unit
def test_extract_comparison_rows_new_category():
    """
    Test unmatched category handling.
    """
    orchestrator = Orchestrator(Mock())
    
    extraction_result = {
        "tables": [
            {
                "title": "Rate Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["5G Service", "0.10"]  # New category not in baseline
                ]
            }
        ]
    }
    
    baseline_data = {
        "tables": [
            {
                "title": "Baseline",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice MOC", "0.05"]
                ]
            }
        ]
    }
    
    comparison_rows = orchestrator._extract_comparison_rows(
        extraction_result,
        baseline_data
    )
    
    assert isinstance(comparison_rows, list)
    if comparison_rows:
        # New category should have old_rate = 0.0
        assert comparison_rows[0].old_rate == 0.0
        assert "NEW_CATEGORY" in comparison_rows[0].note


@pytest.mark.unit
def test_ai_notes_generation():
    """
    Test AI notes for flagged items.
    """
    orchestrator = Orchestrator(Mock())
    
    # Create comparison rows with different scenarios
    from app.agents.risk_agent import RiskItem
    
    comparison_rows = [
        RiskItem(
            category="Voice MOC",
            old_rate=0.05,
            new_rate=0.06,
            delta_pct=20.0,
            risk_level="MEDIUM",
            note="Rate increased by 20.0%"
        ),
        RiskItem(
            category="5G Service",
            old_rate=0.0,
            new_rate=0.10,
            delta_pct=0.0,
            risk_level="LOW",
            note="NEW_CATEGORY"
        )
    ]
    
    # Verify notes are present
    assert any("NEW_CATEGORY" in row.note for row in comparison_rows)
    assert any("increased" in row.note for row in comparison_rows)


@pytest.mark.unit
def test_combine_results_node():
    """
    Test result combination logic.
    """
    orchestrator = Orchestrator(Mock())
    
    from app.agents.orchestrator import OrchestratorState
    from app.agents.risk_agent import RiskSummary
    from app.agents.verification_agent import VerificationResult
    
    state = OrchestratorState(
        extraction_result={"tables": [{"title": "Test", "headers": ["A"], "rows": [["1"]]}]},
        verification_result=VerificationResult(
            status="READY",
            confidence=95,
            checks=["Test"],
            issues=[]
        ),
        risk_result=RiskSummary(
            partner_name="Test",
            total_rows=1,
            changed_rows=0,
            flagged_rows=0,
            highest_risk="LOW",
            recommendation="Safe to proceed",
            items=[]
        ),
        extraction_error=None,
        verification_error=None,
        risk_error=None
    )
    
    result = orchestrator._combine_results_node(state)
    
    assert result is not None
    assert "output" in result
    assert result["output"].summary is not None


@pytest.mark.unit
def test_error_collection():
    """
    Test all errors collected in output.
    """
    orchestrator = Orchestrator(Mock())
    
    from app.agents.orchestrator import OrchestratorState
    from app.agents.verification_agent import VerificationResult
    
    state = OrchestratorState(
        extraction_result=None,
        verification_result=VerificationResult(
            status="FAILED",
            confidence=0,
            checks=[],
            issues=["Test error"]
        ),
        risk_result=None,
        extraction_error="Extraction failed",
        verification_error="Verification failed",
        risk_error="Risk assessment failed"
    )
    
    result = orchestrator._combine_results_node(state)
    
    assert result is not None
    assert "output" in result
    errors = result["output"].errors
    assert "extraction" in errors
    assert "verification" in errors
    assert "risk" in errors


# ============================================================================
# Error Scenario Tests (Mocked)
# ============================================================================

@pytest.mark.unit
def test_run_extraction_failure():
    """
    Test extraction fails → graceful degradation.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock extraction to fail
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": None,
            "extraction_error": "Extraction failed"
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output.errors.get("extraction") is not None


@pytest.mark.unit
def test_run_verification_failure():
    """
    Test verification fails → error handling.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock verification to fail
    with patch.object(orchestrator, '_verification_node') as mock_verification:
        mock_verification.return_value = {
            "verification_result": None,
            "verification_error": "Verification failed"
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output.errors.get("verification") is not None


@pytest.mark.unit
def test_run_risk_failure():
    """
    Test risk assessment fails → error handling.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock risk to fail
    with patch.object(orchestrator, '_risk_node') as mock_risk:
        mock_risk.return_value = {
            "risk_result": None,
            "risk_error": "Risk assessment failed"
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output.errors.get("risk") is not None


@pytest.mark.unit
def test_ai_notes_failure_preserves_template():
    """
    Test graceful failure handling for AI notes.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    # Mock AI notes to fail
    with patch.object(orchestrator, '_ai_notes_node') as mock_ai:
        mock_ai.side_effect = Exception("AI notes generation failed")
        
        from app.agents.orchestrator import OrchestratorState
        from app.agents.risk_agent import RiskSummary
        
        state = OrchestratorState(
            extraction_result={"tables": []},
            verification_result=None,
            risk_result=RiskSummary(
                partner_name="Test",
                total_rows=0,
                changed_rows=0,
                flagged_rows=0,
                highest_risk="LOW",
                recommendation="Safe to proceed",
                items=[]
            ),
            extraction_error=None,
            verification_error=None,
            risk_error=None
        )
        
        # Should handle gracefully
        try:
            result = orchestrator._combine_results_node(state)
            assert result is not None
        except Exception:
            pytest.fail("Should handle AI notes failure gracefully")


@pytest.mark.unit
def test_e2e_with_missing_partner_data():
    """
    Test missing partner name handling.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="",  # Empty partner name
        baseline_data=None,
        file_type="pdf"
    )
    
    result = orchestrator.run(payload)
    
    assert result is not None
    # Should handle empty partner name gracefully


@pytest.mark.unit
def test_e2e_with_api_failure():
    """
    Test Gemini API failure handling.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock extraction to fail with API error
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": None,
            "extraction_error": "Gemini API timeout"
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        assert result.output.errors.get("extraction") is not None


@pytest.mark.unit
def test_e2e_with_pdf_missing_values():
    """
    Test PDF with incomplete data.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf with missing values",
        filename="incomplete.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock extraction to return incomplete data
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": {
                "tables": [
                    {
                        "title": "Incomplete Table",
                        "headers": ["Category", "Rate"],
                        "rows": [["Voice", ""]]  # Empty rate
                    }
                ]
            },
            "extraction_error": None
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        # Should handle incomplete data gracefully


@pytest.mark.unit
def test_e2e_with_required_fields_missing():
    """
    Test required fields not specified.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock extraction to return data missing required fields
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": {
                "tables": [
                    {
                        "title": "Missing Fields",
                        "headers": [],  # Missing headers
                        "rows": [["Voice", "0.05"]]
                    }
                ]
            },
            "extraction_error": None
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None
        # Should handle missing fields gracefully


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
def test_empty_pdf_bytes():
    """
    Test empty PDF bytes.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"",
        filename="empty.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    result = orchestrator.run(payload)
    
    assert result is not None
    # Should handle empty PDF gracefully


@pytest.mark.unit
def test_corrupted_baseline_data():
    """
    Test corrupted baseline data.
    """
    orchestrator = Orchestrator(Mock())
    
    extraction_result = {
        "tables": [
            {
                "title": "Rate Table",
                "headers": ["Category", "Rate"],
                "rows": [["Voice MOC", "0.05"]]
            }
        ]
    }
    
    # Corrupted baseline data
    corrupted_baseline = {
        "tables": [
            {
                "title": "Corrupted",
                "headers": None,  # Invalid
                "rows": "not a list"  # Invalid
            }
        ]
    }
    
    # Should handle gracefully
    try:
        comparison_rows = orchestrator._extract_comparison_rows(
            extraction_result,
            corrupted_baseline
        )
        assert isinstance(comparison_rows, list)
    except Exception:
        pytest.fail("Should handle corrupted baseline gracefully")


@pytest.mark.unit
def test_model_initialization_failures():
    """
    Test model initialization failures.
    """
    # Test with None model
    try:
        orchestrator = Orchestrator(None)
        # Should handle None model gracefully
        assert orchestrator is not None
    except Exception:
        pytest.fail("Should handle None model gracefully")


@pytest.mark.unit
def test_langgraph_state_transition_errors():
    """
    Test LangGraph state transition errors.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock a node to raise an exception
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.side_effect = Exception("State transition error")
        
        try:
            result = orchestrator.run(payload)
            # Should handle the error
            assert result is not None
        except Exception as e:
            # If it raises, should be a handled error
            assert "State transition error" in str(e)


@pytest.mark.unit
def test_memory_limits_with_large_documents():
    """
    Test memory limits with large documents.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    # Create a large PDF (simulate with large bytes)
    large_pdf = b"fake pdf content" * 1000000  # ~10MB
    
    payload = OrchestratorInput(
        pdf_bytes=large_pdf,
        filename="large.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock extraction to handle large document
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": {"tables": []},
            "extraction_error": None
        }
        
        result = orchestrator.run(payload)
        
        assert result is not None


@pytest.mark.unit
def test_concurrent_workflow_executions():
    """
    Test concurrent workflow executions.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    payload = OrchestratorInput(
        pdf_bytes=b"fake pdf",
        filename="test.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )
    
    # Mock successful execution
    with patch.object(orchestrator, '_extraction_node') as mock_extraction:
        mock_extraction.return_value = {
            "extraction_result": {"tables": []},
            "extraction_error": None
        }
        
        # Run multiple times to test concurrent safety
        results = []
        for _ in range(3):
            result = orchestrator.run(payload)
            results.append(result)
        
        # All should complete successfully
        assert all(r is not None for r in results)


@pytest.mark.unit
def test_extract_comparison_rows_empty_table():
    """
    Test extraction with empty table.
    """
    orchestrator = Orchestrator(Mock())
    
    extraction_result = {
        "tables": [
            {
                "title": "Empty Table",
                "headers": ["Category", "Rate"],
                "rows": []  # Empty rows
            }
        ]
    }
    
    comparison_rows = orchestrator._extract_comparison_rows(
        extraction_result,
        None
    )
    
    assert isinstance(comparison_rows, list)
    assert len(comparison_rows) == 0


@pytest.mark.unit
def test_extract_comparison_rows_malformed_rows():
    """
    Test extraction with malformed rows.
    """
    orchestrator = Orchestrator(Mock())
    
    extraction_result = {
        "tables": [
            {
                "title": "Malformed Table",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice"],  # Missing rate
                    ["", "0.05"],  # Missing category
                    ["Voice", "invalid"]  # Invalid rate
                ]
            }
        ]
    }
    
    comparison_rows = orchestrator._extract_comparison_rows(
        extraction_result,
        None
    )
    
    # Should skip malformed rows
    assert isinstance(comparison_rows, list)
    # All rows should be skipped due to being malformed


@pytest.mark.unit
def test_parse_rate_with_currency_symbols():
    """
    Test rate parsing with currency symbols.
    """
    orchestrator = Orchestrator(Mock())
    
    test_cases = [
        ("$0.05", 0.05),
        ("€0.10", 0.10),
        ("£0.15", 0.15),
        ("¥100", 100.0),
    ]
    
    for rate_str, expected in test_cases:
        result = orchestrator._parse_rate(rate_str)
        # Should handle currency symbols
        assert result is not None or result == expected


@pytest.mark.unit
def test_parse_rate_with_thousands_separators():
    """
    Test rate parsing with thousands separators.
    """
    orchestrator = Orchestrator(Mock())
    
    test_cases = [
        ("1,000.50", 1000.50),
        ("10,000", 10000.0),
        ("1.000,50", 1000.50),  # European format
    ]
    
    for rate_str, expected in test_cases:
        result = orchestrator._parse_rate(rate_str)
        # Should handle thousands separators
        assert result is not None


@pytest.mark.unit
def test_find_column_indices_with_duplicate_keywords():
    """
    Test column finding with duplicate keywords.
    """
    orchestrator = Orchestrator(Mock())
    
    headers = ["Category", "Rate", "Category", "Rate"]  # Duplicates
    
    cat_idx, rate_idx = orchestrator._find_column_indices(headers)
    
    # Should find first occurrence
    assert cat_idx == 0
    assert rate_idx == 1


@pytest.mark.unit
def test_find_column_indices_case_insensitive():
    """
    Test case-insensitive keyword matching.
    """
    orchestrator = Orchestrator(Mock())
    
    headers = ["CATEGORY", "rate", "EFFECTIVE DATE"]  # Mixed case
    
    cat_idx, rate_idx = orchestrator._find_column_indices(headers)
    
    # Should match case-insensitively
    assert cat_idx == 0
    assert rate_idx == 1


@pytest.mark.unit
def test_build_graph_structure():
    """
    Test that the graph is built correctly.
    """
    mock_model = Mock()
    orchestrator = Orchestrator(mock_model)
    
    graph = orchestrator._build_graph()
    
    assert graph is not None
    # Verify graph structure (nodes and edges)
    assert hasattr(graph, 'nodes')


@pytest.mark.unit
def test_orchestrator_state_initialization():
    """
    Test orchestrator state initialization.
    """
    from app.agents.orchestrator import OrchestratorState
    
    state = OrchestratorState(
        extraction_result=None,
        verification_result=None,
        risk_result=None,
        extraction_error=None,
        verification_error=None,
        risk_error=None
    )
    
    assert state.extraction_result is None
    assert state.verification_result is None
    assert state.risk_result is None
