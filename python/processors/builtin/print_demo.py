"""Debug/demo processors that print request and response summaries.

Pre-processor logs the outgoing request; post-processor logs the response.
Both are no-ops that pass data through unchanged. Useful for verifying
multi-processor execution order.

Usage in test case YAML:

.. code-block:: yaml

    preprocessors:
      - name: print-demo
        config:
          prefix: "[PreDebug]"   # optional log prefix
    postprocessors:
      - name: print-demo-post
        config:
          prefix: "[PostDebug]"  # optional log prefix
"""

import logging
from typing import Any, Dict, Tuple

from processors.base import PostProcessor, PreProcessor

logger = logging.getLogger(__name__)


class PrintDemoPreProcessor(PreProcessor):
    """Log the request summary at INFO level and pass through unchanged."""

    name = "print-demo"

    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        prefix = case_config.get("prefix", "[PreDemo]")

        header_keys = list(headers.keys())
        body_preview = _truncate(str(body), 200)
        logger.info(
            "%s Request — Headers: %s | Body: %s",
            prefix, header_keys, body_preview,
        )
        return headers, body


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
