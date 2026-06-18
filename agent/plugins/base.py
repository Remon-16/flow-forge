"""Abstract base class for custom case-attribute generator plugins.

Plugins run AFTER assertion generation (Step 3 of the batch pipeline)
and before final YAML/Excel output.  They can add arbitrary attributes
to test cases — most commonly ``preprocessors`` and ``postprocessors``
lists.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PluginDeclaration:
    """Metadata describing what a plugin does and where it applies."""

    plugin_name: str
    """Human-readable name for logging and debugging."""

    attributes: List[str] = field(default_factory=list)
    """Names of the top-level case fields this plugin adds or modifies,
    e.g. ``["preprocessors", "postprocessors"]``."""

    applies_to_single: bool = True
    """Whether this plugin should be run on single-API test cases."""

    applies_to_biz: bool = True
    """Whether this plugin should be run on business-flow test cases."""

    max_retries: int = 1
    """Maximum retries for a batch that fails during ``generate()``."""

    error_strategy: str = "skip"
    """What to do when all retries are exhausted:

    * ``"skip"`` — skip the batch and continue (default)
    * ``"warn"`` — log a warning and continue
    * ``"fail"`` — raise an exception and abort the pipeline
    """


class CaseAttributeGenerator(ABC):
    """Base class for plugins that enrich generated test cases.

    Typical use cases:

    - A **single-case pre-processor agent** analyses each case's
      ``request_body`` / ``request_head`` and decides whether to add
      HMAC signing, parameter encryption, etc. — filling in the
      ``preprocessors`` field.

    - A **biz-flow post-processor agent** analyses the flow execution
      chain and decides whether to add SQL cleanup or Redis refresh
      steps — filling in the ``postprocessors`` field.

    Users write a subclass, place it in a module, and register it via
    the ``PLUGIN_MODULES`` env setting (comma-separated module paths).
    """

    @property
    @abstractmethod
    def declaration(self) -> PluginDeclaration:
        """Return the plugin's metadata declaration."""
        ...

    @abstractmethod
    def generate(
        self,
        cases: List[Dict[str, Any]],
        interfaces: List[Dict[str, Any]],
        api_summary: List[Dict[str, Any]],
        api_doc_text: str,
    ) -> List[Dict[str, Any]]:
        """Generate/update attributes for a batch of test cases.

        Args:
            cases: A batch of completed test cases (single or biz-flow).
                   Each case already has all standard fields filled in
                   (test_id, method, url, request_head, request_body,
                   assert_dict, assert_rules, etc.).
            interfaces: All parsed interface definitions.
            api_summary: API analysis summaries from the analyze_api node.
            api_doc_text: Raw API documentation text.

        Returns:
            The same list of cases with additional attributes added.
            The returned list must have the same length as *cases*.
        """
        ...

    def validate(self, case: Dict[str, Any]) -> List[str]:
        """Optional post-generation validation for a single case.

        Returns a list of human-readable error messages (empty = valid).
        """
        return []
