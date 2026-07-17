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
from collections import defaultdict
from typing import Any, Dict, Tuple

from processors.base import PreProcessor, ProcessorError

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
        # 合并配置：case 级覆盖 env 默认值 / case-level config overrides env defaults
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        # case 级配置覆盖 env 默认值 / case-level config overrides env defaults
        cfg = {**env_config, **case_config}

        algorithm = cfg.get("algorithm", "sha256").lower()
        secret_env = cfg.get("secret_env", "")
        header_name = cfg.get("header_name", "X-Signature")
        body_template = cfg.get(
            "body_template", "{method}\n{path}\n{body}"
        )

        # 优先从 config 直接读取 secret，其次从环境变量
        # Prefer direct secret from config, fall back to env var
        secret = cfg.get("secret") or os.environ.get(secret_env, "")
        if not secret:
            raise ProcessorError(
                f"HMAC secret env var '{secret_env}' is empty or not set",
                processor_name=self.name,
            )

        body_str = json.dumps(body, ensure_ascii=False, sort_keys=True) if body else ""

        # Build the string to sign (simplified; extend as needed)
        # 防御性格式化：用 defaultdict(str) 避免模板中未定义的键导致 KeyError 崩溃
        # Defensive formatting: defaultdict(str) prevents KeyError crash from undefined template keys
        safe_vars = defaultdict(str, {"method": "", "path": "", "body": body_str})
        payload = body_template.format_map(safe_vars)

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
