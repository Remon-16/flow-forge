"""Debug/demo post-processor that prints response summaries.

Usage in test case YAML:

.. code-block:: yaml

    postprocessors:
      - name: print-demo-post
        config:
          prefix: "[PostDebug]"  # optional log prefix
"""

import logging
from typing import Any, Dict

from processors.base import PostProcessor

logger = logging.getLogger(__name__)


class PrintDemoPostProcessor(PostProcessor):
    """Log the response summary at INFO level."""

    name = "print-demo-post"

    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        prefix = case_config.get("prefix", "[PostDemo]")

        resp_header_keys = list(response_headers.keys())
        body_preview = _truncate(str(response_body), 200)
        logger.info(
            "%s Response — Headers: %s | Body: %s",
            prefix, resp_header_keys, body_preview,
        )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
