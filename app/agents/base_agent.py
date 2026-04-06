"""
BaseAgent — shared Anthropic client and structured-output helper.

All agents inherit from this class. The only public primitive is `_parse()`,
which calls the Anthropic Messages API with a Pydantic model as the output schema
and returns the fully-typed, validated result.

API used: client.messages.create() with response_format
  - `instructions` maps to the system parameter
  - `input`        maps to the user message
  - `response_model` is a Pydantic BaseModel subclass; we use JSON mode to enforce schema
"""
import json
import logging
from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

from app.database.connection import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


class BaseAgent:
    """
    Thin wrapper around the Anthropic Messages API with structured outputs.

    Args:
        model: Anthropic model ID. Defaults to claude-3-5-sonnet-20241022
               (best balance of quality/speed/cost for digest workloads).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _parse(self, instructions: str, user_input: str, response_model: type[T]) -> T:
        """
        Call the Anthropic Messages API with structured output.

        Args:
            instructions:   System-level instructions for the model.
            user_input:     The user-turn content (article text, digest list, etc.).
            response_model: A Pydantic BaseModel subclass defining the output schema.

        Returns:
            A fully-validated instance of `response_model`.

        Raises:
            ValueError: If the API returns invalid JSON or fails validation.
        """
        # Get the JSON schema from the Pydantic model
        schema = response_model.model_json_schema()
        
        # Build the prompt with schema instructions
        enhanced_instructions = f"""{instructions}

You must respond with valid JSON that matches this exact schema:
{json.dumps(schema, indent=2)}

Return ONLY the JSON object, no additional text or explanation."""

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=enhanced_instructions,
            messages=[
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        )

        # Extract the text content from the response
        content = response.content[0].text
        
        # Parse the JSON response
        try:
            # Try to extract JSON if there's any markdown formatting
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            json_data = json.loads(content)
            result = response_model.model_validate(json_data)
            return result
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse response as {response_model.__name__}: {e}")
            logger.error(f"Raw response: {content}")
            raise ValueError(
                f"Anthropic API returned invalid JSON for model {response_model.__name__}. "
                f"Error: {e}"
            )