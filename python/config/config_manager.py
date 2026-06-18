import logging
import os
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

_config: Dict[str, Any] = {}
_apps: Dict[str, Dict[str, Any]] = {}
_initialized: bool = False

_REQUIRED_KEYS = ("envName", "caseFilePath")
_TOP_LEVEL_KEYS = {
    "scriptType", "envName", "caseFilePath", "maxThread",
    "reportName", "apiMode", "processor_configs",
}
_DEFAULTS = {
    "scriptType": "APITest",
    "maxThread": 5,
    "reportName": "APIReport",
    "apiMode": "single",
}


class ConfigError(Exception):
    """Raised when configuration validation fails."""


def initialize(yml_path: str, cli_overrides: Optional[Dict[str, Any]] = None) -> None:
    global _config, _apps, _initialized

    if _initialized:
        raise RuntimeError("ConfigManager is already initialized")

    if cli_overrides is None:
        cli_overrides = {}

    try:
        with open(yml_path, "r", encoding="utf-8") as f:
            base_data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {yml_path}")

    _config = dict(_DEFAULTS)
    _config.update(base_data)

    env_name = cli_overrides.get("envName") or _config.get("envName", "")
    config_dir = os.path.dirname(os.path.abspath(yml_path))

    if env_name:
        env_yml_path = os.path.join(config_dir, f"env-{env_name}.yml")
        logger.info("Loading environment config: %s", env_yml_path)
        try:
            with open(env_yml_path, "r", encoding="utf-8") as f:
                env_data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Environment config file not found: {env_yml_path}"
            )

        for key, value in env_data.items():
            if key in _TOP_LEVEL_KEYS:
                _config[key] = value
            elif isinstance(value, dict):
                value["_app_name"] = key
                _apps[key] = value
            else:
                _config[key] = value

    for key, value in cli_overrides.items():
        if value is not None:
            _config[key] = value

    missing = [k for k in _REQUIRED_KEYS if not _config.get(k)]
    if missing:
        raise ConfigError(f"Missing required configuration keys: {missing}")

    _initialized = True
    logger.info(
        "Configuration initialized (env=%s, apiMode=%s, apps=%s)",
        _config["envName"],
        _config.get("apiMode", "single"),
        list(_apps.keys()),
    )


def get(key: str, default: Any = None) -> Any:
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return _config.get(key, default)


def get_all() -> Dict[str, Any]:
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return dict(_config)


def get_app(app_name: str) -> Optional[Dict[str, Any]]:
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return _apps.get(app_name)


def get_apps() -> Dict[str, Dict[str, Any]]:
    if not _initialized:
        raise RuntimeError("ConfigManager has not been initialized")
    return dict(_apps)


def get_processor_config(name: str) -> Dict[str, Any]:
    """Get a named processor config from ``processor_configs``."""
    processor_configs = _config.get("processor_configs", {})
    if isinstance(processor_configs, dict):
        return dict(processor_configs.get(name, {}))
    return {}


def is_initialized() -> bool:
    return _initialized
