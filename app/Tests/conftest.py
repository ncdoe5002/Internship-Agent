"""
Shared fixtures and configuration for agent tests.

This module provides pytest fixtures, marks, and shared test data
for testing extraction, verification, risk, and orchestrator agents.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import Mock, MagicMock, patch
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.extraction import ExtractionResult, TableData


# ============================================================================
# Pytest Marks
# ============================================================================

# Mock the supabase module entirely before Flask app initialization
sys.modules['supabase'] = MagicMock()


# ============================================================================
# Real API Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def real_gemini_model():
    """
    Real LangChain ChatGoogleGenerativeAI configured with test API key.
    
    This fixture is session-scoped to avoid re-initializing the model
    for every test. Requires GOOGLE_API_KEY environment variable.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_API_KEY environment variable not set")
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            GOOGLE_API_KEY=api_key,
            temperature=0.1
        )
        return model
    except ImportError:
        pytest.skip("langchain-google-genai not installed")


@pytest.fixture(scope="session")
def sample_docx_file():
    """
    Orange_IOT_Egypt 2024_sample_tobe_shared.docx file fixture.
    
    Returns the path to the sample document for integration tests.
    """
    docx_path = Path(__file__).parent.parent.parent / "Orange_IOT_Egypt 2024_sample_tobe_shared.docx"
    if not docx_path.exists():
        pytest.skip(f"Sample document not found: {docx_path}")
    return docx_path


@pytest.fixture(scope="session")
def real_extraction_result(real_gemini_model, sample_docx_file):
    """
    Cached extraction result from real API call.
    
    This fixture performs a real extraction and caches the result
    to limit API usage across multiple tests.
    """
    try:
        from app.agents.extraction_agent import ExtractionAgent, ExtractionPayload
        
        with open(sample_docx_file, "rb") as f:
            docx_bytes = f.read()
        
        agent = ExtractionAgent(real_gemini_model)
        payload = ExtractionPayload(
            document_bytes=docx_bytes,
            document_type="docx",
            filename=sample_docx_file.name,
            use_telecom_prompt=True
        )
        
        result = agent.run(payload)
        return result
    except Exception as e:
        pytest.skip(f"Real extraction failed: {e}")


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_gemini_model():
    """
    Mock LangChain ChatGoogleGenerativeAI for unit tests.
    """
    mock_model = Mock()
    mock_model.model = "gemini-1.5-flash"
    
    # Mock invoke method
    mock_response = Mock()
    mock_response.content = '{"tables": [{"title": "Test Table", "headers": ["Category", "Rate"], "rows": [["Voice", "0.05"]]}]}'
    mock_model.invoke.return_value = mock_response
    
    return mock_model


@pytest.fixture
def mock_genai_sdk():
    """
    Mock google.generativeai SDK for error scenarios.
    """
    with patch('google.generativeai') as mock_genai:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text = '{"tables": [{"title": "Test", "headers": ["A", "B"], "rows": [["1", "2"]]}]}'
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        yield mock_genai


@pytest.fixture
def mock_pdf_adapter():
    """
    Mock PDF extraction functions.
    """
    with patch('app.services.extraction.pdf_adapter.extract_text_from_pdf') as mock_text, \
         patch('app.services.extraction.pdf_adapter.pdf_to_images') as mock_images:
        mock_text.return_value = "Sample PDF text content"
        mock_images.return_value = [b"fake_image_bytes"]
        yield mock_text, mock_images


@pytest.fixture
def mock_excel_adapter():
    """
    Mock Excel extraction functions.
    """
    with patch('app.agents.extraction_agent.extract_from_excel') as mock_excel:
        mock_excel.return_value = ExtractionResult(
            tables=[TableData(
                title="Excel Table",
                headers=["Category", "Rate"],
                rows=[["Data", "0.10"]]
            )]
        )
        yield mock_excel


# ============================================================================
# Data Fixtures
# ============================================================================

@pytest.fixture
def sample_extraction_result():
    """
    Valid extraction result with tables.
    """
    return ExtractionResult(
        tables=[
            TableData(
                title="Agreement Header",
                headers=["SENDER", "RP", "START_DATE", "END_DATE", "CURRENCY_CODE"],
                rows=[
                    ["EDCH", "Orange Egypt", "2024-01-01", "2024-12-31", "USD"],
                    ["Orange Egypt", "EDCH", "2024-01-01", "2024-12-31", "USD"]
                ]
            ),
            TableData(
                title="Agreement Rate Details",
                headers=["AGMT_ID", "REC_TYPE", "ZONE_CODE", "RATE_CURRENCY", "PRA_RATE_TYPE", "CHARGE_FIELD"],
                rows=[
                    ["AGM001", "MOC", "Zone1", "USD", "IOT", "CHARGE1"],
                    ["AGM001", "MTC", "Zone1", "USD", "IOT", "CHARGE1"],
                    ["AGM001", "SMS_MO", "Zone1", "USD", "IOT", "CHARGE1"],
                    ["AGM001", "GPRS", "Zone1", "USD", "IOT", "CHARGE1"]
                ]
            )
        ],
        raw_text_summary="Sample extraction from test document"
    )


@pytest.fixture
def sample_baseline_data():
    """
    Baseline tariff data for comparison.
    """
    return {
        "tables": [
            {
                "title": "Current Rates",
                "headers": ["Category", "Rate"],
                "rows": [
                    ["Voice MOC", "0.0182"],
                    ["Voice MTC", "0.0140"],
                    ["SMS MO", "0.0075"],
                    ["Data", "0.0032"],
                    ["SMS MT", "0.0000"]
                ]
            }
        ]
    }


@pytest.fixture
def sample_verification_payload(sample_extraction_result):
    """
    Complete verification input.
    """
    from app.agents.verification_agent import VerificationAgentInput
    
    return VerificationAgentInput(
        partner_name="Orange Egypt",
        extracted_tables=sample_extraction_result.model_dump(),
        baseline_tables=None
    )


@pytest.fixture
def sample_risk_payload():
    """
    Complete risk assessment input.
    """
    from app.agents.risk_agent import RiskAgentInput, RiskItem
    
    return RiskAgentInput(
        partner_name="Orange Egypt",
        confidence=95,
        comparison_rows=[
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
                category="Data",
                old_rate=0.0032,
                new_rate=0.0041,
                delta_pct=28.1,
                risk_level="HIGH",
                note="Rate increased by 28.1%"
            )
        ]
    )


@pytest.fixture
def sample_orchestrator_input():
    """
    Complete orchestrator input with PDF.
    """
    from app.agents.orchestrator import OrchestratorInput
    
    return OrchestratorInput(
        pdf_bytes=b"fake pdf content",
        filename="test_agreement.pdf",
        partner_name="Orange Egypt",
        baseline_data=None,
        file_type="pdf"
    )


# ============================================================================
# Error Fixtures
# ============================================================================

@pytest.fixture
def malformed_json_response():
    """
    Invalid JSON from Gemini.
    """
    return "This is not valid JSON at all"


@pytest.fixture
def empty_pdf_bytes():
    """
    Empty document for edge cases.
    """
    return b""


@pytest.fixture
def incomplete_table_data():
    """
    Tables with missing required fields.
    """
    return ExtractionResult(
        tables=[
            TableData(
                title="Incomplete Table",
                headers=[],  # Missing headers
                rows=[["Voice", "0.05"]]  # Row with no headers
            )
        ]
    )


# ============================================================================
# Test Configuration
# ============================================================================

def pytest_configure(config):
    """
    Configure pytest with custom markers.
    """
    config.addinivalue_line(
        "markers", "unit: Fast unit tests with mocks (no network)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests with real API calls"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end workflow tests"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to execute"
    )


@pytest.fixture(autouse=True)
def setup_logging():
    """
    Configure logging for tests.
    """
    import logging
    logging.basicConfig(level=logging.INFO)
    yield
    logging.shutdown()
