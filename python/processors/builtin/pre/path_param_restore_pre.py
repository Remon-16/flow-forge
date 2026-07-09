"""Restore path parameters that were consumed from the request body.

When ``{id}`` or ``#{id}`` placeholders in the URL are resolved from the
request body, those fields are removed from the body by default.  This
pre-processor reads the cleared fields from
``global_config["_cleared_path_params"]`` and restores them to the body
so the backend receives them as well.

Usage in test case YAML:

.. code-block:: yaml

    preprocessors:
      - name: path-param-restore
        config:
          fields: all               # restore all cleared fields
          # or specify a list:
          # fields: ["id", "uid"]
"""

import logging
from typing import Any, Dict, Tuple

from processors.base import PreProcessor

logger = logging.getLogger(__name__)


class PathParamRestorePreProcessor(PreProcessor):
    """Restore cleared path parameters back into the request body."""

    name = "path-param-restore"

    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cleared = global_config.get("_cleared_path_params")
        if not cleared:
            logger.debug("No cleared path params to restore")
            return headers, body

        fields = case_config.get("fields", "all")

        if fields == "all":
            for key, val in cleared.items():
                body[key] = val
            logger.info("Restored all cleared path params: %s", list(cleared.keys()))
        elif isinstance(fields, list):
            for key in fields:
                if key in cleared:
                    body[key] = cleared[key]
            logger.info("Restored specified path params: %s", fields)
        else:
            logger.warning(
                "Invalid 'fields' config for path-param-restore: %s (expected 'all' or a list)", fields
            )

        return headers, body
