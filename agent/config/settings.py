"""从 YAML 配置文件加载设置并提供默认值。Load settings from YAML config file."""

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List


def get_strategy(rules: List[Dict], check: str, default: str = "fail") -> str:
    """从校验规则列表中查找指定校验的策略。
    Find the strategy for a given check from the validation rules list.

    Args:
        rules: 校验规则列表 / List of {"check": str, "strategy": str} dicts.
        check: 校验名 / Check name to look up.
        default: 未找到时的默认策略 / Default strategy if not found.

    Returns:
        策略值 / Strategy value: "fail", "warn", or "skip".
    """
    for rule in rules:
        if rule.get("check") == check:
            return rule.get("strategy", default)
    return default


def _parse_validation_rules(rules_raw) -> List[Dict[str, str]]:
    """解析校验规则，兼容 dict 和 list 两种 YAML 写法。
    Parse validation rules, supports both dict and list YAML formats.
    """
    if isinstance(rules_raw, list):
        return rules_raw
    if isinstance(rules_raw, dict):
        return [{"check": k, "strategy": v} for k, v in rules_raw.items()]
    return []


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
    auto_mode: bool = False

    # 骨架生成分批大小 / Skeleton generation batch size
    skeleton_batch_size: int = 30

    # 计划生成分块大小（每个分块包含的接口数）/ Plan chunk size (interfaces per chunk)
    # 已废弃，请使用 plan_single_batch_size + plan_biz_flow_batch_size
    # Deprecated — use plan_single_batch_size + plan_biz_flow_batch_size instead
    plan_chunk_size: int = 0

    # 单接口测试点分组大小（-1=不拆分，强模型建议 -1）/ Single API batch size (-1=no split)
    plan_single_batch_size: int = 8

    # 业务链路每批合并数（-1=不拆分，强模型建议 -1）/ Biz flow batch size (-1=no split)
    plan_biz_flow_batch_size: int = 3

    # 是否将日志持久化到 output_dir/logs/agent.log / Persist logs to output_dir
    # 默认关闭，输出文件已较多，有需要的用户自行开启 / Default off, enable on demand
    logging_log_to_output: bool = False

    # 校验规则列表 / Validation rules list
    # 每项为 {"check": "<校验名>", "strategy": "fail|warn|skip"}
    # Each entry: {"check": "<check_name>", "strategy": "fail|warn|skip"}
    validation_rules: List[Dict[str, str]] = field(default_factory=lambda: [
        {"check": "skeleton_count", "strategy": "fail"},
        {"check": "url_check", "strategy": "warn"},
        {"check": "data_fill_count", "strategy": "fail"},
        {"check": "assertion_count", "strategy": "fail"},
    ])

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
            "auto_mode": self.auto_mode,
            "skeleton_batch_size": self.skeleton_batch_size,
            "plan_chunk_size": self.plan_chunk_size,
            "plan_single_batch_size": self.plan_single_batch_size,
            "plan_biz_flow_batch_size": self.plan_biz_flow_batch_size,
            "logging_log_to_output": self.logging_log_to_output,
            "validation_rules": self.validation_rules,
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
    logging_cfg = config.get("logging", {})

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
        skeleton_batch_size=int(pipeline.get("skeleton_batch_size", 30)),
        plan_chunk_size=int(pipeline.get("plan_chunk_size", 0)),
        validation_rules=_parse_validation_rules(validation.get("rules", {})),
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
        auto_mode=pipeline.get("auto", False),
        logging_log_to_output=logging_cfg.get("log_to_output", False),
    )

    # 为 i18n 设置语言（i18n 懒加载时通过 os.environ 读取）
    # Set language for i18n lazy init via os.environ
    os.environ["AGENT_LANG"] = settings.agent_lang

    # ---- 向后兼容：plan_chunk_size → plan_single_batch_size + plan_biz_flow_batch_size ----
    # Backward compat: migrate old plan_chunk_size to the two new config fields
    _plan_chunk = int(pipeline.get("plan_chunk_size", 0))
    _plan_single_raw = pipeline.get("plan_single_batch_size")
    _plan_biz_raw = pipeline.get("plan_biz_flow_batch_size")

    if _plan_single_raw is None and _plan_chunk > 0:
        settings.plan_single_batch_size = _plan_chunk
    elif _plan_single_raw is not None:
        settings.plan_single_batch_size = int(_plan_single_raw)

    if _plan_biz_raw is None and _plan_chunk > 0:
        settings.plan_biz_flow_batch_size = _plan_chunk
    elif _plan_biz_raw is not None:
        settings.plan_biz_flow_batch_size = int(_plan_biz_raw)

    return settings
