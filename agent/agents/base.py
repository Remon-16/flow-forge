"""BaseAgent with LLM call, retry, and structured output parsing."""

import json
import logging
import re
import time
from typing import Any, Callable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class ConvergenceError(Exception):
    """Raised when an agent exceeds its max_steps limit."""


class BaseAgent:
    """Base class for all LLM-powered agents.

    Provides:
    - OpenAI-compatible LLM call
    - Automatic retry with exponential backoff
    - Structured JSON output parsing
    - Step counter with max_steps guard
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
        max_steps: int = 10,
    ):
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._max_steps = max_steps
        self._step_count = 0

    def check_step(self) -> None:
        """Increment step counter, raise if max_steps exceeded."""
        self._step_count += 1
        if self._step_count > self._max_steps:
            raise ConvergenceError(
                f"Agent exceeded max_steps ({self._max_steps})"
            )

    def reset_steps(self) -> None:
        self._step_count = 0

    def call_llm(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
        response_format: Optional[str] = None,
    ) -> str:
        """Call LLM with retry. Returns raw text response."""
        self.check_step()

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                }

                if response_format == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}

                response = self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt, self._max_retries, e,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM call failed after {self._max_retries} attempts: {last_error}"
        )

    def call_llm_json(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
    ) -> Any:
        """Call LLM and parse response as JSON."""
        text = self.call_llm(prompt, system_msg, response_format="json_object")
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse JSON from LLM response.

        Handles responses wrapped in ```json fences or plain text.
        """
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` fence
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try extracting from ``` ... ``` fence
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find a JSON object/array in the text
        brace_match = re.search(r'\{[\s\S]*\}', text)
        bracket_match = re.search(r'\[[\s\S]*\]', text)

        for m in (brace_match, bracket_match):
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Failed to parse JSON from LLM response:\n{text[:500]}")
