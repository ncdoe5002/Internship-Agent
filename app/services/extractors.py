import logging
from app.services.prompts import ROAMING_AGREEMENT_PROMPT, GENERIC_TABLE_EXTRACTION_PROMPT
from app.services.llm_client import chat_complete_json

logger = logging.getLogger(__name__)

def extract_roaming_agreement(contract_text: str) -> dict:
    """
    Extracts the 5 core staging tables from a telecom roaming agreement.
    Uses the strict JSON schema defined in ROAMING_AGREEMENT_PROMPT.
    """
    logger.info("Sending roaming agreement to local LLM for extraction...")
    
    # We pass the friend's prompt as the system prompt, and the document text as the user prompt
    extracted_data = chat_complete_json(
        prompt=f"DOCUMENT TEXT TO ANALYZE:\n{contract_text}",
        system_prompt=ROAMING_AGREEMENT_PROMPT
    )
    
    return extracted_data

def extract_generic_document(document_text: str) -> dict:
    """
    Fallback extractor for non-roaming agreements using the generic table prompt.
    """
    logger.info("Sending generic document to local LLM for extraction...")
    
    extracted_data = chat_complete_json(
        prompt=f"DOCUMENT TEXT TO ANALYZE:\n{document_text}",
        system_prompt=GENERIC_TABLE_EXTRACTION_PROMPT
    )
    
    return extracted_data