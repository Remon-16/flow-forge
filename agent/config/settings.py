"""从 YAML 配置文件加载设置并提供默认值。Load settings from YAML config file."""

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List


def get_strategy(validation_rules: List[Dict], check: str, default: str = "fail") -> str:
    """从校验规则列表中查找指定校验的策略。
    Find the strategy for a given check from the validation rules list.

    Args:
        validation_rules: 校验规则列表 / List of {"check": str, "strategy": str} dicts.
        check: 校验名 / Check name to look up.
        default: 未找到时的默认策略 / Default strategy if not found.

    Returns:
        策略值 / Strategy value: "fail", "warn", or "skip".
    """
    for rule in validation_rules:
        if rule.get("check") == check:
            return rule.get("strategy", default)
    return default


def get_url_failure_action(validation_rules: List[Dict], default: str = "discard") -> str:
    """从校验规则列表中查找 url_check 的 failure_action 子规则。
    Find the failure_action sub-rule from the url_check rule entry.

    仅当 url_check 的 strategy 为 "warn" 时生效（fail 直接抛异常，skip 无失败用例）。
    Only meaningful when url_check strategy is "warn".

    Args:
        validation_rules: 校验规则列表 / List of validation rule dicts.
        default: 未找到时的默认动作 / Default action if not found.

    Returns:
        失败处理动作 / Failure action: "discard" | "keep".
    """
    for rule in validation_rules:
        if rule.get("check") == "url_check":
            action = rule.get("failure_action", default)
            if action not in ("discard", "keep"):
                return default
            return action
    return default


def _parse_validation_rules(rules_raw) -> List[Dict[str, str]]:
    """解析校验规则，兼容 dict 和 list 两种 YAML 写法。
    Parse validation rules, supports both dict and list YAML formats.

    dict 格式支持两种写法：
      - {"url_check": "warn"} → [{"check": "url_check", "strategy": "warn"}]
      - {"url_check": {"strategy": "warn", "failure_action": "keep"}}
        → [{"check": "url_check", "strategy": "warn", "failure_action": "keep"}]
    """
    if isinstance(rules_raw, list):
        return rules_raw
    if isinstance(rules_raw, dict):
        result = []
        for check, val in rules_raw.items():
            if isinstance(val, dict):
                entry = {"check": check}
                entry.update(val)
                result.append(entry)
            else:
                result.append({"check": check, "strategy": val})
        return result
    return []


def _ensure_list(value):
    """规范化值为列表，处理 YAML 中字符串/列表两种写法。
    Normalize value to list — handle both string and list forms in YAML.

    用户可能误将单个模块路径写成字符串而非列表：
    User may write a single module path as a string instead of a list:
        modules: "a.b.Class"    →   ["a.b.Class"]
        modules: ["a.b.Class"]  →   ["a.b.Class"]
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return []


@dataclass
class Settings:
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.3
    llm_context_window: int = 128000
    llm_context_compression_threshold: float = 0.9
    llm_max_output_tokens: int = 4096
    # 知识库功能已下线，代码保留以备将来恢复。默认 False 确保不启用。
    # Knowledge base feature is disabled. Code preserved for future restoration. Default False.
    enable_knowledge: bool = False
    knowledge_dir: str = "./knowledge"
    max_steps: int = 10
    max_retries: int = 3
    llm_rate_limit_delay: float = 0.0
    llm_retry_base_delay: float = 2.0
    output_dir: str = "./output"
    plugin_batch_size: int = 10
    case_format_max_retries: int = 3
    output_format: str = "both"
    url_doc_match_max_retries: int = 3
    url_doc_match_strategy: str = "warn"
    enable_plugins: bool = False
    plugin_modules: List[str] = field(default_factory=list)
    llm_max_concurrency: int = 1
    consecutive_batch_failure_limit: int = 3
    llm_request_timeout: float = 600.0
    llm_extra_params: Dict[str, Any] = field(default_factory=dict)
    agent_lang: str = "zh_CN"
    enable_skills: bool = True
    skill_agents: Dict[str, List[str]] = field(default_factory=dict)
    auto_mode: bool = False

    # 用例生成类型 / Case generation type: both | single | biz
    case_type: str = "both"

    # 骨架生成分批大小 / Skeleton generation batch size
    skeleton_batch_size: int = 30

    # 单接口测试点分组大小（-1=不拆分，强模型建议 -1）/ Single API batch size (-1=no split)
    plan_single_batch_size: int = 8

    # 业务链路每批合并数 / Biz flow batch size
    # 预留：逐流 Mermaid 生成要求必须为 1 / Reserved: per-flow Mermaid requires 1
    plan_biz_flow_batch_size: int = 1

    # 是否将日志持久化到 output_dir/logs/agent.log / Persist logs to output_dir
    # 默认关闭，输出文件已较多，有需要的用户自行开启 / Default off, enable on demand
    logging_log_to_output: bool = False

    # URL 文档匹配校验开关 / Enable URL doc-match validation
    url_doc_match_enabled: bool = True

    # 校验规则列表 / Validation rules list
    # 每项为 {"check": "<校验名>", "strategy": "fail|warn|skip"}
    # Each entry: {"check": "<check_name>", "strategy": "fail|warn|skip"}
    case_gen_validation: List[Dict[str, str]] = field(default_factory=lambda: [
        {"check": "skeleton_count", "strategy": "warn"},
        {"check": "url_check", "strategy": "warn"},
        {"check": "data_fill_count", "strategy": "warn"},
        {"check": "assertion_count", "strategy": "warn"},
        {"check": "processor_count", "strategy": "warn"},
    ])

    # 计划解析校验 / Parse plan validation
    # 独立的配置块，与 case_gen_validation 平级 / Independent config block, peer of case_gen_validation
    parse_plan_validation_enabled: bool = True
    parse_plan_validation_max_retries: int = 3
    parse_plan_validation_rules: List[Dict[str, str]] = field(default_factory=lambda: [
        {"check": "flow_match", "strategy": "warn"},
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_api_key": "***",
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
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
            "plugin_batch_size": self.plugin_batch_size,
            "case_format_max_retries": self.case_format_max_retries,
            "output_format": self.output_format,
            "url_doc_match_max_retries": self.url_doc_match_max_retries,
            "url_doc_match_strategy": self.url_doc_match_strategy,
            "enable_plugins": self.enable_plugins,
            "plugin_modules": self.plugin_modules,
            "llm_max_concurrency": self.llm_max_concurrency,
            "consecutive_batch_failure_limit": self.consecutive_batch_failure_limit,
            "llm_request_timeout": self.llm_request_timeout,
            "llm_extra_params": self.llm_extra_params,
            "enable_skills": self.enable_skills,
            "skill_agents": self.skill_agents,
            "auto_mode": self.auto_mode,
            "skeleton_batch_size": self.skeleton_batch_size,
            "plan_single_batch_size": self.plan_single_batch_size,
            "plan_biz_flow_batch_size": self.plan_biz_flow_batch_size,
            "logging_log_to_output": self.logging_log_to_output,
            "case_type": self.case_type,
            "url_doc_match_enabled": self.url_doc_match_enabled,
            "case_gen_validation": self.case_gen_validation,
            "parse_plan_validation_enabled": self.parse_plan_validation_enabled,
            "parse_plan_validation_max_retries": self.parse_plan_validation_max_retries,
            "parse_plan_validation_rules": self.parse_plan_validation_rules,
        }


def _read_url_doc_match_enabled(validation: Dict) -> bool:
    """读取 URL 文档匹配校验开关 / Read URL doc-match validation enable flag.

    优先级 / Priority:
      1. url_doc_match_validation.enable（新路径 / new path）
      2. url_doc_match_rules.enable（旧路径 / old path）
      3. 默认 True / Default True
    """
    # 新路径 / New path
    block = validation.get("url_doc_match_validation", {})
    if isinstance(block, dict):
        enable = block.get("enable")
        if enable is not None:
            return bool(enable)
    # 旧路径 / Old path
    old_block = validation.get("url_doc_match_rules", {})
    if isinstance(old_block, dict):
        enable = old_block.get("enable")
        if enable is not None:
            return bool(enable)
    return True


def _read_url_doc_match_max_retries(validation: Dict) -> int:
    """读取 URL 文档匹配重试次数 / Read URL doc-match max retries.

    优先级 / Priority:
      1. url_doc_match_validation.max_retries（新路径 / new path）
      2. url_doc_match_rules.max_retries（旧 block 路径 / old block path）
      3. url_doc_match_max_retries（旧平铺 key / old flat key）
      4. 默认 3 / Default 3
    """
    # 新路径 / New path
    block = validation.get("url_doc_match_validation", {})
    if isinstance(block, dict) and "max_retries" in block:
        return int(block["max_retries"])
    # 旧 block 路径 / Old block path
    old_block = validation.get("url_doc_match_rules", {})
    if isinstance(old_block, dict) and "max_retries" in old_block:
        return int(old_block["max_retries"])
    # 旧平铺 key / Old flat key
    return int(validation.get("url_doc_match_max_retries", 3))


def _read_url_doc_match_strategy(validation: Dict) -> str:
    """读取 URL 文档匹配策略 / Read URL doc-match strategy.

    优先级 / Priority:
      1. url_doc_match_validation.rules 列表中 url_check 的 strategy
      2. url_doc_match_validation.strategy（block 级平铺 / block-level flat）
      3. url_doc_match_rules.rules 列表中 url_check 的 strategy
      4. url_doc_match_rules.strategy（旧 block 级平铺 / old block-level flat）
      5. 默认 "warn" / Default "warn"
    """
    # 新路径：从 rules 列表中查找 url_check / New path: find url_check in rules list
    block = validation.get("url_doc_match_validation", {})
    if isinstance(block, dict):
        rules = block.get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict) and rule.get("check") == "url_check":
                    return rule.get("strategy", "warn")
        # 新 block 级平铺 / New block-level flat
        if "strategy" in block:
            return block["strategy"]
    # 旧路径 / Old path
    old_block = validation.get("url_doc_match_rules", {})
    if isinstance(old_block, dict):
        rules = old_block.get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict) and rule.get("check") == "url_check":
                    return rule.get("strategy", "warn")
        if "strategy" in old_block:
            return old_block["strategy"]
    return "warn"


# _read_case_gen_enabled() — 预留给将来实现 / Reserved for future implementation
# 当前代码路径不需要此函数，因为所有校验均设为 skip 策略
# Currently unused because all validation rules are set to "skip"


def _read_case_gen_max_retries(validation: Dict) -> int:
    """读取用例格式校验重试次数 / Read case format validation max retries.

    优先级 / Priority:
      1. case_gen_validation.max_retries（新路径 / new path）
      2. case_gen_rules.max_retries（旧 block 路径 / old block path）
      3. case_format_max_retries（旧平铺 key / old flat key）
      4. 默认 3 / Default 3
    """
    # 新路径 / New path
    block = validation.get("case_gen_validation", {})
    if isinstance(block, dict) and "max_retries" in block:
        return int(block["max_retries"])
    # 旧 block 路径 / Old block path
    old_block = validation.get("case_gen_rules", {})
    if isinstance(old_block, dict) and "max_retries" in old_block:
        return int(old_block["max_retries"])
    # 旧平铺 key / Old flat key
    return int(validation.get("case_format_max_retries", 3))


def _extract_case_gen_rules_raw(validation: Dict):
    """提取 case_gen 校验规则原始数据 / Extract case gen validation rules raw data.

    优先级 / Priority:
      1. case_gen_validation.rules（新路径 / new path）
      2. case_gen_validation 直接作为列表/dict（兼容 / compat）
      3. case_gen_rules.rules（旧 block 路径 / old block path）
      4. case_gen_rules 直接作为列表/dict（旧格式 / old format）
      5. 默认 {} / Default {}
    """
    # 新路径 / New path
    block = validation.get("case_gen_validation", {})
    if isinstance(block, dict):
        if "rules" in block:
            return block["rules"]
        # 如果 block 不含 rules key 但也不是列表，可能整个 block 就是规则本身
    elif isinstance(block, list):
        return block
    # 旧路径 / Old path
    old_block = validation.get("case_gen_rules", {})
    if isinstance(old_block, dict):
        if "rules" in old_block:
            return old_block["rules"]
        return old_block
    if isinstance(old_block, list):
        return old_block
    return {}


def _read_parse_plan_validation_enabled(validation: Dict) -> bool:
    """读取计划解析校验开关 / Read parse plan validation enable flag.

    优先级 / Priority:
      1. parse_plan_validation.enable
      2. 默认 True / Default True
    """
    block = validation.get("parse_plan_validation", {})
    if isinstance(block, dict):
        return bool(block.get("enable", True))
    return True


def _read_parse_plan_validation_max_retries(validation: Dict) -> int:
    """读取计划解析校验最大重试次数 / Read parse plan validation max retries.

    优先级 / Priority:
      1. parse_plan_validation.max_retries
      2. 默认 3 / Default 3
    """
    block = validation.get("parse_plan_validation", {})
    if isinstance(block, dict):
        return int(block.get("max_retries", 3))
    return 3


def _parse_parse_plan_validation_rules(validation: Dict) -> List[Dict[str, str]]:
    """读取计划解析校验规则 / Read parse plan validation rules.

    优先级 / Priority:
      1. parse_plan_validation.rules（列表格式 / list format）
      2. 默认 [{"check": "flow_match", "strategy": "warn"}] / Default
    """
    block = validation.get("parse_plan_validation", {})
    if isinstance(block, dict):
        rules = block.get("rules", [])
        if isinstance(rules, list):
            return rules
    return [{"check": "flow_match", "strategy": "warn"}]


def get_flow_match_failure_action(
    validation_rules: List[Dict], default: str = "discard",
) -> str:
    """从校验规则列表中查找 flow_match 的 failure_action 子规则。
    Find the failure_action sub-rule from flow_match in the validation rules list.

    仅当 flow_match 的 strategy 为 "warn" 时生效（fail 直接抛异常，skip 无失败场景）。
    Only meaningful when flow_match strategy is "warn".

    Args:
        validation_rules: 校验规则列表 / List of validation rule dicts.
        default: 未找到时的默认动作 / Default action if not found.

    Returns:
        失败处理动作 / Failure action: "discard" | "keep".
    """
    for rule in validation_rules:
        if rule.get("check") == "flow_match":
            action = rule.get("failure_action", default)
            if action not in ("discard", "keep"):
                return default
            return action
    return default


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
        llm_extra_params=llm.get("extra_params", {}),
        enable_knowledge=knowledge.get("enabled", False),
        knowledge_dir=knowledge.get("dir", "./knowledge"),
        max_steps=int(pipeline.get("max_steps", 10)),
        max_retries=int(pipeline.get("max_retries", 3)),
        consecutive_batch_failure_limit=int(pipeline.get("consecutive_batch_failure_limit", 3)),
        skeleton_batch_size=int(pipeline.get("skeleton_batch_size", 30)),
        plan_single_batch_size=int(pipeline.get("plan_single_batch_size", 8)),
        # 校验规则（新路径 case_gen_validation.rules，回退旧路径）
        # Validation rules (new path case_gen_validation.rules, fallback old paths)
        case_gen_validation=_parse_validation_rules(_extract_case_gen_rules_raw(validation)),
        case_format_max_retries=_read_case_gen_max_retries(validation),
        # 计划解析校验（新路径 parse_plan_validation）/ Parse plan validation (new path)
        parse_plan_validation_enabled=_read_parse_plan_validation_enabled(validation),
        parse_plan_validation_max_retries=_read_parse_plan_validation_max_retries(validation),
        parse_plan_validation_rules=_parse_parse_plan_validation_rules(validation),
        # URL 文档匹配（新路径 url_doc_match_validation，回退旧路径 url_doc_match_rules）
        # URL doc-match (new path url_doc_match_validation, fallback old path url_doc_match_rules)
        url_doc_match_enabled=_read_url_doc_match_enabled(validation),
        url_doc_match_max_retries=_read_url_doc_match_max_retries(validation),
        url_doc_match_strategy=_read_url_doc_match_strategy(validation),
        output_dir=output.get("dir", "./output"),
        plugin_batch_size=int(pipeline.get("plugin_batch_size", 10)),
        output_format=output.get("format", "both"),
        enable_plugins=plugins.get("enabled", False),
        plugin_modules=_ensure_list(plugins.get("modules", [])),
        enable_skills=skills_cfg.get("enabled", True),
        skill_agents=skills_cfg.get("agents", {}),
        agent_lang=agent_cfg.get("lang", "zh_CN"),
        auto_mode=pipeline.get("auto", False),
        case_type=pipeline.get("case_type", "both"),
        logging_log_to_output=logging_cfg.get("log_to_output", False),
    )

    # 为 i18n 设置语言（i18n 懒加载时通过 os.environ 读取）
    # Set language for i18n lazy init via os.environ
    os.environ["AGENT_LANG"] = settings.agent_lang

    return settings
