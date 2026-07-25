"""
gemini.py — DEPRECATED.

This module previously initialised a LangChain / Google Gemini model.
The application has been migrated to a local-first architecture:
all LLM calls now go through ``app.services.llm_client`` which targets
the LM Studio OpenAI-compatible API.

This file is kept as a stub to avoid ImportError in any code that has
not yet been updated.  Nothing here creates a real model or makes any
network call.

If you see this imported somewhere, update that import to use
``app.services.llm_client`` instead.
"""

import logging

logger = logging.getLogger(__name__)


def get_langchain_model(*args, **kwargs):  # type: ignore[no-untyped-def]
    """
    Deprecated.  Previously returned a ChatGoogleGenerativeAI instance.

    Raises:
        NotImplementedError: Always — use llm_client.chat_complete() instead.
    """
    raise NotImplementedError(
        "get_langchain_model() has been removed. "
        "Use app.services.llm_client.chat_complete() or "
        "app.services.llm_client.chat_complete_json() instead."
    )
