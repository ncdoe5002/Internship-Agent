import json
import logging
import math
from openai import OpenAI

logger = logging.getLogger(__name__)

# Point directly to your local LM Studio server
# Using host.docker.internal allows the Docker container to see the host machine
client = OpenAI(base_url="http://host.docker.internal:1234/v1", api_key="lm-studio")

def calculate_confidence_score(api_response: dict) -> int:
    """
    Calculates an overall confidence percentage (0-100) based on token logprobs.
    """
    try:
        choices = api_response.get("choices", [])
        if not choices:
            return 0
            
        logprobs_data = choices[0].get("logprobs")
        if not logprobs_data or not logprobs_data.get("content"):
            return 0
            
        tokens = logprobs_data.get("content", [])
        if not tokens:
            return 0
            
        total_probability = 0.0
        
        for token_data in tokens:
            logprob = token_data.get("logprob", 0.0)
            probability = math.exp(logprob)  # Convert logprob to actual probability
            total_probability += probability
            
        average_probability = total_probability / len(tokens)
        return int(average_probability * 100)
    except Exception as e:
        logger.warning(f"Failed to calculate logprobs confidence: {e}")
        return 0

def chat_complete_json(prompt: str, system_prompt: str, max_retries: int = 3) -> dict:
    """
    Queries the local Gemma model via LM Studio and forces a valid JSON response.
    Includes a self-correction loop if the model returns malformed text.
    """
    current_prompt = prompt

    for attempt in range(max_retries):
        dynamic_temp = 0.1 + (attempt * 0.2)
        try:
            response = client.chat.completions.create(
                model="local-model", # LM Studio intercepts this and uses whatever model is loaded
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": current_prompt}
                ],
                temperature=dynamic_temp,
                logprobs=True,  # Request logprobs for confidence 
                top_logprobs=1,
            )
            
            raw_output = response.choices[0].message.content
            if not raw_output:
                return {}
            
            # Strip out markdown code blocks if the LLM adds them
            if isinstance(raw_output, str):
                raw_output = raw_output.replace('```json', '').replace('```', '').strip()

            # 1. Parse the text into a dictionary first
            extracted_dict = json.loads(raw_output)

            # 2. Convert the OpenAI response object to a dict so your helper function can read it
            response_dict = response.model_dump() 
            
            # 3. Calculate the score
            score = calculate_confidence_score(response_dict)
            
            # 4. Inject the score into the final payload
            extracted_dict["confidence_score"] = score
            
            return extracted_dict

        except json.JSONDecodeError:
            logger.warning(f"Attempt {attempt + 1} failed. Model returned invalid JSON. Retrying...")
            error_msg = f"Your previous response was not valid JSON. Please fix it. Previous output: {raw_output}"
            current_prompt = f"{prompt}\n\nSystem Error: {error_msg}"
            
    raise ValueError("LLM failed to return valid JSON after multiple attempts.")

def chat_complete(prompt: str, system_prompt: str) -> str:
    """
    Standard text completion for tasks that do not require JSON formatting.
    """
    response = client.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or ""
