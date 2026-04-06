"""
BaseAgent — shared OpenAI client and structured-output helper.

All agents inherit from this class.  The only public primitive is `_parse()`,
which calls the Responses API with a Pydantic model as the output schema and
returns the fully-typed, validated result.

API used: client.responses.parse()  (openai >= 2.0)
  - `instructions` maps to the system turn
  - `input`        maps to the user turn
  - `text_format`  is a Pydantic BaseModel subclass; the SDK enforces the JSON
                   schema at the API level and deserialises the result automatically
  - `.output_parsed` holds the typed Pydantic instance
"""
import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.database.connection import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gpt-4o-mini"


class BaseAgent:
    """
    Thin wrapper around the OpenAI Responses API.

    Args:
        model: OpenAI model ID. Defaults to gpt-4o-mini (best cost/speed for
               digest-scale workloads; swap to gpt-4o for higher quality).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def _parse(self, instructions: str, user_input: str, response_model: type[T]) -> T:
        """
        Call the Responses API with structured output.

        Args:
            instructions:   System-level instructions for the model.
            user_input:     The user-turn content (article text, digest list, etc.).
            response_model: A Pydantic BaseModel subclass defining the output schema.

        Returns:
            A fully-validated instance of `response_model`.

        Raises:
            ValueError: If the API returns a null parsed result (should not happen
                        with a well-formed schema, but guards against it explicitly).
        """
        response = self._client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=user_input,
            text_format=response_model,
        )

        result = response.output_parsed
        if result is None:
            raise ValueError(
                f"Responses API returned null output for model {response_model.__name__}. "
                "Check that the schema has no Optional fields without defaults at the top level."
            )
        return result
