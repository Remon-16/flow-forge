"""HMAC-SHA256 response verification post-processor.

Validates that a response carries a valid HMAC signature.  Computes the
expected signature from the response body and compares it against the
value in a response header.  Raises :class:`ProcessorError` on mismatch.

This is the counterpart of :class:`HmacSignPreProcessor` and can be used
for end-to-end request/response signing scenarios.

Usage in test case YAML:

.. code-block:: yaml

    postprocessors:
      - name: hmac-verify
        config:
          algorithm: sha256          # optional, default sha256
          secret_env: SIGN_SECRET    # env var holding the shared secret
          header_name: X-Signature   # optional, default X-Signature
          body_template: "{body}"    # optional

Sensitive config can be placed in ``env.yml`` under
``processor_configs.hmac-verify`` and will be merged automatically.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict

from processors.base import PostProcessor, ProcessorError

logger = logging.getLogger(__name__)


class HmacVerifyPostProcessor(PostProcessor):
    """Verify an HMAC-SHA256 signature on the response."""

    name = "hmac-verify"

    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**case_config, **env_config}

        algorithm = cfg.get("algorithm", "sha256").lower()
        secret_env = cfg.get("secret_env", "")
        header_name = cfg.get("header_name", "X-Signature")
        body_template = cfg.get("body_template", "{body}")

        secret = os.environ.get(secret_env, "")
        if not secret:
            logger.warning(
                "HMAC verify secret env var '%s' is empty or not set", secret_env
            )

        expected = response_headers.get(header_name)
        if not expected:
            raise ProcessorError(
                f"HMAC signature header '{header_name}' not found in response",
                processor_name=self.name,
            )

        if response_body is None:
            body_str = ""
        elif isinstance(response_body, str):
            body_str = response_body
        else:
            body_str = json.dumps(response_body, ensure_ascii=False, sort_keys=True)

        payload = body_template.format(body=body_str)

        if algorithm == "sha256":
            actual = hmac.new(
                secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        else:
            raise ProcessorError(
                f"Unsupported HMAC algorithm: {algorithm}",
                processor_name=self.name,
            )

        if not hmac.compare_digest(actual, expected):
            raise ProcessorError(
                f"HMAC signature mismatch in response header '{header_name}'",
                processor_name=self.name,
            )

        logger.debug("HMAC-SHA256 signature verified on response header '%s'", header_name)
