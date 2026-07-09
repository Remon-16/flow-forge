"""翻译智能体配置加载。

Translator settings loader — completely independent from the main pipeline config.
Does NOT read env.yaml — the two configs are independent.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class TranslateSettings:
    """翻译智能体配置 / Translator settings."""

    # LLM settings
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: str = ""
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 4096
    llm_context_window: int = 128000
    llm_max_concurrency: int = 1
    llm_rate_limit_delay: float = 0.0
    llm_retry_base_delay: float = 2.0
    llm_request_timeout: float = 600.0
    llm_extra_params: Dict[str, Any] = field(default_factory=dict)

    # Translate settings
    target_lang: str = "zh_CN"
    batch_size: int = 10
    detection_enabled: bool = True
    cjk_threshold: float = 0.5

    # Logging
    log_to_output: bool = False


def load_translate_settings(config_path: str) -> TranslateSettings:
    """从 translate_env.yaml 加载翻译配置。

    Load translator settings from translate_env.yaml.
    This function does NOT read env.yaml — the two configs are independent.

    Args:
        config_path: translate_env.yaml 文件路径 / Path to translate_env.yaml.

    Returns:
        TranslateSettings dataclass instance.

    Raises:
        FileNotFoundError: 配置文件不存在 / Config file not found.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    llm_cfg = raw.get("llm", {})
    translate_cfg = raw.get("translate", {})
    detection_cfg = translate_cfg.get("detection", {})
    logging_cfg = raw.get("logging", {})

    return TranslateSettings(
        # LLM settings
        llm_provider=llm_cfg.get("provider", "openai"),
        llm_api_key=llm_cfg.get("api_key", ""),
        llm_model=llm_cfg.get("model", "gpt-4o"),
        llm_base_url=llm_cfg.get("base_url", ""),
        llm_temperature=float(llm_cfg.get("temperature", 0.1)),
        llm_max_output_tokens=int(llm_cfg.get("max_output_tokens", 4096)),
        llm_context_window=int(llm_cfg.get("context_window", 128000)),
        llm_max_concurrency=int(llm_cfg.get("max_concurrency", 1)),
        llm_rate_limit_delay=float(llm_cfg.get("rate_limit_delay", 0.0)),
        llm_retry_base_delay=float(llm_cfg.get("retry_base_delay", 2.0)),
        llm_request_timeout=float(llm_cfg.get("request_timeout", 600.0)),
        llm_extra_params=llm_cfg.get("extra_params", {}),
        # Translate settings
        target_lang=translate_cfg.get("target_lang", "zh_CN"),
        batch_size=int(translate_cfg.get("batch_size", 10)),
        detection_enabled=bool(detection_cfg.get("enabled", True)),
        cjk_threshold=float(detection_cfg.get("cjk_threshold", 0.5)),
        # Logging
        log_to_output=bool(logging_cfg.get("log_to_output", False)),
    )
