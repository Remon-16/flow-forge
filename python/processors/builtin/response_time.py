"""Response metrics post-processor.

Logs the response status code and content length.  Warns when the response
body exceeds a configurable size threshold.

Usage in test case YAML:

.. code-block:: yaml

    postprocessors:
      - name: response-time
        config:
          warn_threshold_bytes: 1048576   # optional, default 1048576 (1 MB)
"""

import logging
from typing import Any, Dict

from processors.base import PostProcessor

logger = logging.getLogger(__name__)


class ResponseTimePostProcessor(PostProcessor):
    """Log response status code and content length."""

    name = "response-time"

    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        warn_threshold = case_config.get("warn_threshold_bytes", 1048576)  # 1 MB default

        content_length_header = response_headers.get("Content-Length")
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
            except (ValueError, TypeError):
                content_length = None
        else:
            content_length = None

        # Fall back to computing length from the response body
        if content_length is None and response_body is not None:
            content_length = len(str(response_body).encode("utf-8"))

        if content_length is not None:
            logger.info(
                "Response metrics — Content-Length: %d bytes",
                content_length,
            )
            if content_length > warn_threshold:
                logger.warning(
                    "Response body size %d bytes exceeds threshold %d bytes",
                    content_length, warn_threshold,
                )
        else:
            logger.info("Response metrics — Content-Length: unknown")
