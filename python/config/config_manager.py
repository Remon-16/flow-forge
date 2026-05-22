import logging
from copy import deepcopy
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

_config: Dict[str, Any] = {}
_initialized: bool = False

_REQUIRED_KEYS = ("baseURL", "envName", "caseFilePath")
_DEFAULTS = {
    "scriptType": "APITest",
    "maxThread": 5,
    "reportName": "APIReport",
}


class ConfigError(Exception):
    """Raised when configuration validation fails."""


def initialize(yml_path: str, cli_overrides: Optional[Dict[str, Any]] = None) -> None:
    """Load configuration from a YAML file and merge CLI overrides.

    Must be called once before any other ConfigManager method.
    Raises ConfigError on validation failure, FileNotFoundError if yml is missing.
    """
    global _config, _initialized

    if _initialized:
        raise RuntimeError("ConfigManager is already initialized")

    try:
        with open(yml_path, "r", encoding="utf-8") as f:
            yml_data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {yml_path}")

    _config = dict(_DEFAULTS)
    _config.update(yml_data)

    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                _config[key] = value

    missing = [k for k in _REQUIRED_KEYS if not _config.get(k)]
    if missing:
        raise ConfigError(f"Missing required configuration keys: {missing}")

    _initialized = True
    logger.info("Configuration initialized (env=%s, scriptType=%s)", _config["envName"], _config["scriptType"])


def get(key: str, default: Any = None) -> Any:
    """Return a single configuration value."""
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return _config.get(key, default)


def get_all() -> Dict[str, Any]:
    """Return a shallow copy of the entire configuration dict."""
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return dict(_config)


def is_initialized() -> bool:
    return _initialized
