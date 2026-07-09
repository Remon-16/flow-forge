"""LLM Token counter with tiktoken support and character-based fallback."""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

_MODEL_ENCODING_MAP: Dict[str, str] = {
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "deepseek-v3": "cl100k_base",
    "deepseek-v4": "cl100k_base",
    "deepseek-v4-flash": "cl100k_base",
    "deepseek-v4-pro": "cl100k_base",
    "deepseek-r1": "cl100k_base",
    "deepseek-chat": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "claude-3-opus": "cl100k_base",
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-3.5-sonnet": "cl100k_base",
}


def _resolve_encoding(model: str) -> str:
    """Resolve tiktoken encoding name from model name."""
    if model in _MODEL_ENCODING_MAP:
        return _MODEL_ENCODING_MAP[model]
    for prefix, enc in [
        ("gpt-4o", "o200k_base"),
        ("gpt-4", "cl100k_base"),
        ("gpt-3.5", "cl100k_base"),
        ("deepseek", "cl100k_base"),
        ("claude", "cl100k_base"),
    ]:
        if model.startswith(prefix):
            return enc
    return "cl100k_base"


class TokenCounter:
    """LLM Token counter.

    Supports two counting modes:
    - tiktoken: accurate counting via the tiktoken library (requires ``pip install tiktoken``)
    - chars: rough estimation using ``len(text) / 4`` (zero-dependency fallback)

    Each instance is independent; multiple instances can coexist without shared state.
    """

    def __init__(self, model: str = "gpt-4o"):
        self._model = model
        self._encoding_name = _resolve_encoding(model)
        self._encoder = None
        self._mode: str = "chars"

        try:
            import tiktoken
            self._encoder = tiktoken.get_encoding(self._encoding_name)
            self._mode = "tiktoken"
        except Exception:
            logger.info(
                "tiktoken not available for model '%s' (encoding '%s'), "
                "using chars/4 estimation. Install tiktoken for accurate counting.",
                model, self._encoding_name,
            )

    def count(self, text: str) -> int:
        """Count tokens in a single text string."""
        if not text:
            return 0
        if self._mode == "tiktoken" and self._encoder is not None:
            return len(self._encoder.encode(text))
        return len(text) // 4

    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """Count total tokens across a list of chat messages.

        Each message is a dict with 'role' and 'content' keys.
        Includes a small overhead per message (~4 tokens for role/metadata).
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            total += self.count(content)
            total += 4
        return total

    def estimate_request(
        self,
        system_msg: str,
        user_prompt: str,
        output_reserve: int = 0,
    ) -> int:
        """Estimate total token consumption for a single LLM call.

        Returns the sum of: system message + user prompt + output reserve.
        Does NOT include conversation history (that is tracked separately
        by the agent instance).
        """
        total = self.count(system_msg)
        total += self.count(user_prompt)
        total += output_reserve
        return total

    @property
    def mode(self) -> str:
        """Return current counting mode: 'tiktoken' or 'chars'."""
        return self._mode

    @property
    def encoding_name(self) -> str:
        """Return the resolved encoding name."""
        return self._encoding_name
