"""HMAC-SHA256 signature preprocessor.

Usage in test case YAML:

.. code-block:: yaml

    preprocessors:
      - name: hmac-sign
        config:
          algorithm: sha256          # optional, default sha256
          secret_env: SIGN_SECRET    # env var name holding the secret
          header_name: X-Signature   # optional, default X-Signature
          body_template: "{method}\n{path}\n{body}"  # optional

Sensitive config (e.g. the secret env var name) can also be placed in
``env.yml`` under ``processor_configs.hmac-sign`` and will be merged
with the case-level config automatically.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Tuple

from processors.base import PreProcessor

logger = logging.getLogger(__name__)


class HmacSignPreProcessor(PreProcessor):
    """Compute an HMAC-SHA256 signature and attach it to the request headers."""

    name = "hmac-sign"

    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # Merge config: global processor_configs take precedence for secrets
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**case_config, **env_config}

        algorithm = cfg.get("algorithm", "sha256").lower()
        secret_env = cfg.get("secret_env", "")
        header_name = cfg.get("header_name", "X-Signature")
        body_template = cfg.get(
            "body_template", "{method}\n{path}\n{body}"
        )

        secret = os.environ.get(secret_env, "")
        if not secret:
            logger.warning(
                "HMAC secret env var '%s' is empty or not set", secret_env
            )

        body_str = json.dumps(body, ensure_ascii=False, sort_keys=True) if body else ""

        # Build the string to sign (simplified; extend as needed)
        payload = body_template.format(
            method="",  # caller can inject via case-level config if needed
            path="",
            body=body_str,
        )

        if algorithm == "sha256":
            digest = hmac.new(
                secret.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        else:
            raise ValueError(f"Unsupported HMAC algorithm: {algorithm}")

        headers[header_name] = digest
        logger.debug("HMAC-SHA256 signature added to header '%s'", header_name)

        return headers, body
