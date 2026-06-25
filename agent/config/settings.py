"""从 YAML 配置文件加载设置并提供默认值。Load settings from YAML config file."""

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Settings:
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_context_window: int = 128000
    llm_context_compression_threshold: float = 0.9
    llm_max_output_tokens: int = 4096
    enable_knowledge: bool = False
    knowledge_dir: str = "./knowledge"
    max_steps: int = 10
    max_retries: int = 3
    llm_rate_limit_delay: float = 0.0
    llm_retry_base_delay: float = 2.0
    output_dir: str = "./output"
    batch_size: int = 10
    enable_validation: bool = True
    max_validation_retries: int = 3
    output_format: str = "both"
    max_steps_no_progress: int = 5
    url_correction_max_retries: int = 3
    enable_plugins: bool = False
    plugin_modules: List[str] = field(default_factory=list)
    llm_max_concurrency: int = 1
    consecutive_batch_failure_limit: int = 3
    llm_request_timeout: float = 600.0
    agent_lang: str = "zh_CN"
    enable_skills: bool = True
    skill_agents: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_api_key": "***",
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_context_window": self.llm_context_window,
            "llm_context_compression_threshold": self.llm_context_compression_threshold,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "enable_knowledge": self.enable_knowledge,
            "knowledge_dir": self.knowledge_dir,
            "max_steps": self.max_steps,
            "max_retries": self.max_retries,
            "llm_rate_limit_delay": self.llm_rate_limit_delay,
            "llm_retry_base_delay": self.llm_retry_base_delay,
            "output_dir": self.output_dir,
            "batch_size": self.batch_size,
            "enable_validation": self.enable_validation,
            "max_validation_retries": self.max_validation_retries,
            "output_format": self.output_format,
            "max_steps_no_progress": self.max_steps_no_progress,
            "url_correction_max_retries": self.url_correction_max_retries,
            "enable_plugins": self.enable_plugins,
            "plugin_modules": self.plugin_modules,
            "llm_max_concurrency": self.llm_max_concurrency,
            "consecutive_batch_failure_limit": self.consecutive_batch_failure_limit,
            "llm_request_timeout": self.llm_request_timeout,
            "enable_skills": self.enable_skills,
            "skill_agents": self.skill_agents,
        }


def load_settings(yaml_path: str = "env.yaml") -> Settings:
    """从 YAML 配置文件加载设置。Load settings from YAML config file.

    文件不存在时返回默认配置。Returns Settings with defaults when file is missing.
    """
    config: Dict[str, Any] = {}
    if os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    llm = config.get("llm", {})
    pipeline = config.get("pipeline", {})
    knowledge = config.get("knowledge", {})
    validation = config.get("validation", {})
    output = config.get("output", {})
    plugins = config.get("plugins", {})
    skills_cfg = config.get("skills", {})
    agent_cfg = config.get("agent", {})

    settings = Settings(
        llm_provider=llm.get("provider", "openai"),
        llm_api_key=llm.get("api_key", ""),
        llm_base_url=llm.get("base_url", ""),
        llm_model=llm.get("model", "gpt-4o"),
        llm_temperature=float(llm.get("temperature", 0.3)),
        llm_max_output_tokens=int(llm.get("max_output_tokens", 4096)),
        llm_context_window=int(llm.get("context_window", 128000)),
        llm_context_compression_threshold=float(llm.get("context_compression_threshold", 0.9)),
        llm_max_concurrency=int(llm.get("max_concurrency", 1)),
        llm_rate_limit_delay=float(llm.get("rate_limit_delay", 0.0)),
        llm_retry_base_delay=float(llm.get("retry_base_delay", 2.0)),
        llm_request_timeout=float(llm.get("request_timeout", 600.0)),
        enable_knowledge=knowledge.get("enabled", False),
        knowledge_dir=knowledge.get("dir", "./knowledge"),
        max_steps=int(pipeline.get("max_steps", 10)),
        max_retries=int(pipeline.get("max_retries", 3)),
        max_steps_no_progress=int(pipeline.get("max_steps_no_progress", 5)),
        consecutive_batch_failure_limit=int(pipeline.get("consecutive_batch_failure_limit", 3)),
        url_correction_max_retries=int(pipeline.get("url_correction_max_retries", 3)),
        enable_validation=validation.get("enabled", True),
        max_validation_retries=int(validation.get("max_retries", 3)),
        output_dir=output.get("dir", "./output"),
        batch_size=int(output.get("batch_size", 10)),
        output_format=output.get("format", "both"),
        enable_plugins=plugins.get("enabled", False),
        plugin_modules=plugins.get("modules", []),
        enable_skills=skills_cfg.get("enabled", True),
        skill_agents=skills_cfg.get("agents", {}),
        agent_lang=agent_cfg.get("lang", "zh_CN"),
    )

    # 为 i18n 设置语言（i18n 懒加载时通过 os.environ 读取）
    # Set language for i18n lazy init via os.environ
    os.environ["AGENT_LANG"] = settings.agent_lang

    return settings
