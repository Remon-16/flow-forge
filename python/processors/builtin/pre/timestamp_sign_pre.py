"""Timestamp and request-id injection preprocessor.

Adds ``X-Timestamp`` (ISO 8601 UTC) and ``X-Request-Id`` (UUIDv4) headers
to every request. Useful for request tracing and multi-processor chaining tests.

Usage in test case YAML:

.. code-block:: yaml

    preprocessors:
      - name: timestamp
        config:
          header_timestamp: X-Timestamp     # optional, default X-Timestamp
          header_request_id: X-Request-Id   # optional, default X-Request-Id
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from processors.base import PreProcessor

logger = logging.getLogger(__name__)


class TimestampPreProcessor(PreProcessor):
    """Inject X-Timestamp and X-Request-Id headers."""

    name = "timestamp"

    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        header_timestamp = case_config.get("header_timestamp", "X-Timestamp")
        header_request_id = case_config.get("header_request_id", "X-Request-Id")

        ts = datetime.now(timezone.utc).isoformat()
        req_id = str(uuid.uuid4())

        headers[header_timestamp] = ts
        headers[header_request_id] = req_id

        logger.debug("Injected %s=%s, %s=%s", header_timestamp, ts, header_request_id, req_id)
        return headers, body
