import logging
import os
from typing import Any, Dict, Optional

import yaml

from i18n import _, set_lang

logger = logging.getLogger(__name__)

_config: Dict[str, Any] = {}
_apps: Dict[str, Dict[str, Any]] = {}
_initialized: bool = False

_REQUIRED_KEYS = ("envName", "caseFilePath")
# 仅用于校验的 CLI 覆盖键（不写入最终配置）/ Validation-only CLI override keys (not stored into final config)
_VALIDATION_ONLY_KEYS = {"yamlDir", "yamlFiles"}
_TOP_LEVEL_KEYS = {
    "scriptType", "envName", "caseFilePath", "maxThread",
    "reportName", "apiMode", "processor_configs",
}
_DEFAULTS = {
    "scriptType": "APITest",
    "maxThread": 5,
    "reportName": "APIReport",
    "apiMode": "single",
    "lang": "zh_CN",
    "excel_font": "微软雅黑",
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
        if value is not None and key not in _VALIDATION_ONLY_KEYS:
            _config[key] = value

    # 提供 --yamlDir/--yamlFiles 时，caseFilePath 不再是必填键（YAML 输入不依赖 Excel 路径）。
    # When --yamlDir/--yamlFiles is provided, caseFilePath is not required (YAML input doesn't use it).
    yaml_input_given = bool(cli_overrides.get("yamlDir") or cli_overrides.get("yamlFiles"))
    missing = [
        key for key in _REQUIRED_KEYS
        if (key != "caseFilePath" or not yaml_input_given) and not _config.get(key)
    ]
    if missing:
        # 确保翻译已加载（默认 zh_CN），避免 _() 返回 key 本身。
        # Ensure translations are loaded (default zh_CN) so _() returns text, not the key.
        set_lang(os.environ.get("AGENT_LANG", "").strip() or "zh_CN")
        raise ConfigError(_("config.missing_required_keys", keys=", ".join(missing)))

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


def is_initialized() -> bool:
    return _initialized
