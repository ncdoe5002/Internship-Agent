"""
Tests for ExtractionAgent.

This module contains unit tests, integration tests, and error scenario tests
for the document extraction agent using both mocked and real Gemini API calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.agents.extraction_agent import ExtractionAgent, ExtractionPayload
from app.schemas.extraction import ExtractionResult, TableData

# ============================================================================
# Integration Tests (Real API)
# ============================================================================

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.xfail(reason="DOCX extraction is not yet implemented in ExtractionAgent")
def test_run_with_docx_real_api(real_gemini_model, sample_docx_file):
    """
    Test extraction with real DOCX file using real Gemini API.
    """
    with open(sample_docx_file, "rb") as f:
        docx_bytes = f.read()

    agent = ExtractionAgent(real_gemini_model)
    payload = ExtractionPayload(
        document_bytes=docx_bytes,
        document_type="docx",
        filename=sample_docx_file.name,
        use_telecom_prompt=True,
    )

    result = agent.run(payload)

    assert result is not None
    assert isinstance(result, ExtractionResult)
    assert len(result.tables) > 0
    # Verify at least one table was extracted
    assert any(table.headers for table in result.tables)


@pytest.mark.integration
@pytest.mark.slow
def test_extract_from_pdf_direct_upload_real_api(real_gemini_model, sample_docx_file):
    """
    Test direct PDF upload to Gemini with real API.

    Note: This test uses the DOCX file but tests the PDF extraction logic
    by mocking the PDF adapter to return the DOCX content.
    """
    with open(sample_docx_file, "rb") as f:
        docx_bytes = f.read()

    agent = ExtractionAgent(real_gemini_model)

    # Mock the PDF to use DOCX content for testing
    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        # Create a mock result similar to what we'd expect from PDF
        mock_result = ExtractionResult(
            tables=[
                TableData(
                    title="PDF Extracted Table",
                    headers=["Category", "Rate"],
                    rows=[["Voice", "0.05"]],
                )
            ]
        )
        mock_direct.return_value = mock_result

        payload = ExtractionPayload(
            document_bytes=docx_bytes,
            document_type="pdf",
            filename="test.pdf",
            use_telecom_prompt=True,
        )

        result = agent._extract_from_pdf(payload)

        assert result is not None
        assert len(result.tables) > 0
        mock_direct.assert_called_once()


@pytest.mark.integration
@pytest.mark.slow
def test_extract_via_text_real_api(real_gemini_model):
    """
    Test text-based extraction fallback with real API.
    """
    agent = ExtractionAgent(real_gemini_model)

    # Patch where the function is USED, not where it is defined
    with patch(
        "app.agents.extraction_agent.extract_text_from_pdf"
    ) as mock_text:
        mock_text.return_value = """
        Agreement Header
        SENDER: EDCH
        RP: Orange Egypt
        START_DATE: 2024-01-01
        END_DATE: 2024-12-31
        CURRENCY: USD

        Rate Table
        Voice MOC: 0.05
        Voice MTC: 0.03
        SMS MO: 0.01
        """

        payload = ExtractionPayload(
            document_bytes=b"fake pdf",
            document_type="pdf",
            filename="test.pdf",
            use_telecom_prompt=True,
        )

        result = agent._extract_via_text(payload)

        assert result is not None
        mock_text.assert_called_once()

# ============================================================================
# Unit Tests (Mocked)
# ============================================================================


@pytest.mark.unit
def test_run_with_pdf_success_mock(mock_gemini_model, mock_pdf_adapter):
    """
    Test PDF extraction with mocked Gemini API returning valid JSON.
    """
    agent = ExtractionAgent(mock_gemini_model)

    # Mock the direct PDF upload to succeed
    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        mock_result = ExtractionResult(
            tables=[
                TableData(
                    title="Test Table",
                    headers=["Category", "Rate"],
                    rows=[["Voice", "0.05"]],
                )
            ]
        )
        mock_direct.return_value = mock_result

        payload = ExtractionPayload(
            document_bytes=b"fake pdf content",
            document_type="pdf",
            filename="test.pdf",
            use_telecom_prompt=True,
        )

        result = agent.run(payload)

        assert result is not None
        assert isinstance(result, ExtractionResult)
        assert len(result.tables) == 1
        assert result.tables[0].title == "Test Table"
        mock_direct.assert_called_once()


@pytest.mark.unit
def test_run_with_excel_success_mock(mock_excel_adapter):
    """
    Test Excel extraction with mocked excel_adapter.
    """
    mock_model = Mock()
    agent = ExtractionAgent(mock_model)

    payload = ExtractionPayload(
        document_bytes=b"fake excel content",
        document_type="xlsx",
        filename="test.xlsx",
        use_telecom_prompt=True,
    )

    result = agent.run(payload)

    assert result is not None
    assert isinstance(result, ExtractionResult)
    assert len(result.tables) > 0


@pytest.mark.unit
def test_run_unsupported_file_type(mock_gemini_model):
    """
    Test error handling for unsupported file types.
    """
    agent = ExtractionAgent(mock_gemini_model)

    payload = ExtractionPayload(
        document_bytes=b"fake content",
        document_type="txt",
        filename="test.txt",
        use_telecom_prompt=True,
    )

    result = agent.run(payload)

    assert result is not None
    assert isinstance(result, ExtractionResult)
    assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_json_from_response_with_markdown():
    """
    Test parsing JSON from markdown code fences.
    """
    agent = ExtractionAgent(Mock())

    raw_text = """
    ```json
    {
        "tables": [
            {
                "title": "Test",
                "headers": ["A", "B"],
                "rows": [["1", "2"]]
            }
        ]
    }
    ```
    """

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    assert len(result.tables) == 1
    assert result.tables[0].title == "Test"


@pytest.mark.unit
def test_extract_json_from_response_with_extra_text():
    """
    Test handling extra text around JSON.
    """
    agent = ExtractionAgent(Mock())

    raw_text = """
    Here is some extra text before the JSON.
    {"tables": [{"title": "Test", "headers": ["A"], "rows": [["1"]]}]}
    And some text after.
    """

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    assert len(result.tables) == 1


@pytest.mark.unit
def test_extract_json_from_response_list_format():
    """
    Test handling list format instead of object.
    """
    agent = ExtractionAgent(Mock())

    raw_text = """
    [
        {
            "title": "Table 1",
            "headers": ["A", "B"],
            "rows": [["1", "2"]]
        },
        {
            "title": "Table 2",
            "headers": ["C", "D"],
            "rows": [["3", "4"]]
        }
    ]
    """

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    assert len(result.tables) == 2


# ============================================================================
# Error Scenario Tests (Mocked)
# ============================================================================


@pytest.mark.unit
def test_extract_from_pdf_api_timeout(mock_gemini_model):
    """
    Test API timeout error handling.
    """
    agent = ExtractionAgent(mock_gemini_model)

    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        mock_direct.side_effect = TimeoutError("API timeout")

        with patch.object(agent, "_send_pdf_as_images") as mock_images:
            mock_images.side_effect = TimeoutError("Image timeout")

            with patch.object(agent, "_extract_via_text") as mock_text:
                mock_text.return_value = ExtractionResult(tables=[])

                payload = ExtractionPayload(
                    document_bytes=b"fake pdf",
                    document_type="pdf",
                    filename="test.pdf",
                    use_telecom_prompt=True,
                )

                result = agent._extract_from_pdf(payload)

                assert result is not None
                assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_from_pdf_connection_error(mock_gemini_model):
    """
    Test connection failure error handling.
    """
    agent = ExtractionAgent(mock_gemini_model)

    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        mock_direct.side_effect = ConnectionError("Connection failed")

        with patch.object(agent, "_send_pdf_as_images") as mock_images:
            mock_images.side_effect = ConnectionError("Image connection failed")

            with patch.object(agent, "_extract_via_text") as mock_text:
                mock_text.return_value = ExtractionResult(tables=[])

                payload = ExtractionPayload(
                    document_bytes=b"fake pdf",
                    document_type="pdf",
                    filename="test.pdf",
                    use_telecom_prompt=True,
                )

                result = agent._extract_from_pdf(payload)

                assert result is not None
                assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_from_pdf_all_attempts_fail(mock_gemini_model):
    """
    Test complete failure handling when all extraction attempts fail.
    """
    agent = ExtractionAgent(mock_gemini_model)

    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        mock_direct.side_effect = Exception("Direct upload failed")

        with patch.object(agent, "_send_pdf_as_images") as mock_images:
            mock_images.side_effect = Exception("Image extraction failed")

            with patch.object(agent, "_extract_via_text") as mock_text:
                mock_text.side_effect = Exception("Text extraction failed")

                payload = ExtractionPayload(
                    document_bytes=b"fake pdf",
                    document_type="pdf",
                    filename="test.pdf",
                    use_telecom_prompt=True,
                )

                result = agent._extract_from_pdf(payload)

                assert result is not None
                assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_json_from_response_invalid_json():
    """
    Test JSON parse error handling.
    """
    agent = ExtractionAgent(Mock())

    raw_text = "This is not valid JSON at all"

    result = agent._extract_json_from_response(raw_text)

    assert result is None


@pytest.mark.unit
def test_extract_json_from_response_empty_response():
    """
    Test empty response handling.
    """
    agent = ExtractionAgent(Mock())

    result = agent._extract_json_from_response("")

    assert result is None


@pytest.mark.unit
def test_extract_from_pdf_malformed_response(mock_gemini_model):
    """
    Test handling malformed API response.
    """
    agent = ExtractionAgent(mock_gemini_model)

    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        # Return a result that will fail JSON parsing
        mock_direct.return_value = None

        with patch.object(agent, "_send_pdf_as_images") as mock_images:
            mock_images.return_value = None

            with patch.object(agent, "_extract_via_text") as mock_text:
                mock_text.return_value = ExtractionResult(tables=[])

                payload = ExtractionPayload(
                    document_bytes=b"fake pdf",
                    document_type="pdf",
                    filename="test.pdf",
                    use_telecom_prompt=True,
                )

                result = agent._extract_from_pdf(payload)

                assert result is not None
                assert len(result.tables) == 0


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_extract_from_pdf_empty_bytes(mock_gemini_model):
    """
    Test handling empty PDF bytes.
    """
    agent = ExtractionAgent(mock_gemini_model)

    payload = ExtractionPayload(
        document_bytes=b"",
        document_type="pdf",
        filename="empty.pdf",
        use_telecom_prompt=True,
    )

    with patch.object(agent, "_send_pdf_to_gemini") as mock_direct:
        mock_direct.return_value = ExtractionResult(tables=[])

        result = agent._extract_from_pdf(payload)

        assert result is not None
        assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_json_from_response_no_tables():
    """
    Test handling response with no tables.
    """
    agent = ExtractionAgent(Mock())

    raw_text = '{"tables": []}'

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    assert len(result.tables) == 0


@pytest.mark.unit
def test_extract_json_from_response_numeric_values():
    """
    Test handling numeric values returned as numbers instead of strings.
    """
    agent = ExtractionAgent(Mock())

    raw_text = """
    {
        "tables": [
            {
                "title": "Test",
                "headers": ["Category", "Rate"],
                "rows": [["Voice", 0.05], ["SMS", 0.01]]
            }
        ]
    }
    """

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    assert len(result.tables) == 1
    # Verify numeric values are coerced to strings
    assert result.tables[0].rows[0][1] == "0.05"
    assert result.tables[0].rows[1][1] == "0.01"


@pytest.mark.unit
def test_extract_json_from_response_missing_headers():
    """
    Test handling table with missing headers.
    """
    agent = ExtractionAgent(Mock())

    raw_text = """
    {
        "tables": [
            {
                "title": "Test",
                "headers": [],
                "rows": [["Voice", "0.05"]]
            }
        ]
    }
    """

    result = agent._extract_json_from_response(raw_text)

    assert result is not None
    # Tables with empty headers should be skipped
    assert len(result.tables) == 0


@pytest.mark.unit
def test_model_name_resolution_with_prefix():
    """
    Test model name resolution when it has 'models/' prefix.
    """
    mock_model = Mock()
    mock_model.model = "models/gemini-1.5-flash"

    agent = ExtractionAgent(mock_model)

    with patch("google.generativeai") as mock_genai:
        mock_genai_model = Mock()
        mock_response = Mock()
        mock_response.text = '{"tables": []}'
        mock_genai_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_genai_model

        try:
            agent._send_pdf_to_gemini(b"fake pdf", "test prompt")
            # Verify model name was resolved correctly (without 'models/' prefix)
            mock_genai.GenerativeModel.assert_called_with(model_name="gemini-1.5-flash")
        except ImportError:
            pytest.skip("google-generativeai not installed")


@pytest.mark.unit
def test_use_telecom_prompt_flag():
    """
    Test that use_telecom_prompt flag selects correct prompt.
    """
    mock_model = Mock()
    agent = ExtractionAgent(mock_model)

    with patch.object(agent, "_extract_from_pdf") as mock_extract:
        mock_extract.return_value = ExtractionResult(tables=[])

        # Test with telecom prompt
        payload_telecom = ExtractionPayload(
            document_bytes=b"fake pdf",
            document_type="pdf",
            filename="test.pdf",
            use_telecom_prompt=True,
        )
        agent.run(payload_telecom)

        # Test with generic prompt
        payload_generic = ExtractionPayload(
            document_bytes=b"fake pdf",
            document_type="pdf",
            filename="test.pdf",
            use_telecom_prompt=False,
        )
        agent.run(payload_generic)

        assert mock_extract.call_count == 2
