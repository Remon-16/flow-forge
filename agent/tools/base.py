"""Base tool interface for the tool registry system."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class BaseTool:
    """A callable tool registered in the ToolRegistry.

    Attributes:
        name: Unique tool name (used in LLM tool_choice).
        description: Natural-language description for the LLM.
        func: The Python callable.
        parameters: JSON Schema for the toolʼs parameters (auto-generated
            from type hints when possible, or supplied explicitly).
    """

    name: str
    description: str
    func: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __call__(self, *args, **kwargs) -> Any:
        return self.func(*args, **kwargs)

    def to_openai_spec(self) -> Dict[str, Any]:
        """Return an OpenAI-compatible tool definition dict."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
