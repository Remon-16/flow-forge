"""Abstract base classes and registry for Pre/Post processors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type

# ---------------------------------------------------------------------------
# Global registries (populated automatically via __init_subclass__)
# ---------------------------------------------------------------------------
_PRE_PROCESSOR_REGISTRY: Dict[str, Type["PreProcessor"]] = {}
_POST_PROCESSOR_REGISTRY: Dict[str, Type["PostProcessor"]] = {}


def _register_pre_processor(cls: Type["PreProcessor"]) -> None:
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(f"PreProcessor subclass {cls.__name__} must define a 'name' class attribute")
    _PRE_PROCESSOR_REGISTRY[name] = cls


def _register_post_processor(cls: Type["PostProcessor"]) -> None:
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(f"PostProcessor subclass {cls.__name__} must define a 'name' class attribute")
    _POST_PROCESSOR_REGISTRY[name] = cls


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ProcessorError(Exception):
    """Controlled error from a processor — message flows into the test report."""

    def __init__(self, message: str, processor_name: str = ""):
        super().__init__(message)
        self.processor_name = processor_name


# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------

class PreProcessor(ABC):
    """Base class for pre-request processors.

    Subclasses are auto-registered by ``name``.  Place your ``.py`` file in
    the ``processors/`` directory and it will be discovered at runtime.
    """

    name: str  # Must be set on each subclass (used as registry key)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_pre_processor(cls)

    def can_process(self, case: Dict[str, Any]) -> bool:
        """Override to conditionally skip this processor for a given case."""
        return True

    @abstractmethod
    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Modify request headers and/or body before the request is sent.

        Args:
            headers: Current request headers (mutable copy).
            body: Current request body (mutable copy).
            case_config: Inline ``config`` dict from the test case.
            global_config: Full merged environment configuration
                (includes ``processor_configs`` top-level key).

        Returns:
            ``(modified_headers, modified_body)``.

        Raises:
            ProcessorError: Abort the test case with an error message
                that appears in the report.
        """
        ...


class PostProcessor(ABC):
    """Base class for post-response processors.

    Subclasses are auto-registered by ``name``.
    """

    name: str  # Must be set on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_post_processor(cls)

    @abstractmethod
    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        """Inspect or post-process the response after assertions have run.

        Args:
            request_headers: Headers that were sent.
            request_body: Body that was sent.
            response_headers: Response headers (dict).
            response_body: Parsed response body (JSON object, list, or string).
            case_config: Inline ``config`` dict from the test case.
            global_config: Full merged environment configuration.

        Raises:
            ProcessorError: Record a post-processing error in the report.
        """
        ...
