# llm_client.py
import json, os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="OPENROUTER_API_KEY",
)


MODEL_NAME = "openai/gpt-oss-20b:free"


def chat_complete_json(prompt: str, system_prompt: str, max_retries: int = 3) -> dict:
    """
    Queries OpenRouter model and forces valid JSON response.
    """

    current_prompt = prompt

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": current_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=8000,
            )

            raw_output = response.choices[0].message.content

            if not raw_output:
                logger.warning("OpenRouter returned empty response")
                return {}

            # Remove markdown wrapping if returned
            raw_output = raw_output.replace("```json", "").replace("```", "").strip()

            extracted_dict = json.loads(raw_output)

            return extracted_dict

        except json.JSONDecodeError:

            logger.warning(
                f"Attempt {attempt + 1}: Invalid JSON returned by OpenRouter"
            )

            current_prompt = f"""
            Your previous response failed JSON parsing. 
            Ensure all quotes are closed, no trailing commas exist, and the response is wrapped in valid JSON syntax.

            Original Extraction Target:
            {prompt}
            """

        except Exception as e:

            logger.warning(f"OpenRouter request failed attempt {attempt + 1}: {e}")

    raise ValueError("OpenRouter failed to return valid JSON after retries")


def chat_complete(prompt: str, system_prompt: str) -> str:
    """
    Standard text completion for non JSON tasks.
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    return response.choices[0].message.content or ""
