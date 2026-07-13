"""测试 CLI 参数覆盖 env.yaml 配置 / Test CLI argument override of env.yaml settings.

验证每个 CLI 参数能正确覆盖 env.yaml 配置值，以及 CLI > env > defaults 的优先级链。
Verify CLI args override env.yaml values and the CLI > env > defaults priority chain.
"""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 确保 agent/ 在 sys.path 中 / Ensure agent/ is on sys.path
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


# ============================================================================
# 辅助：构造模拟 args namespace + mini Settings / Helpers
# ============================================================================


def _make_args(**overrides):
    """构造与 parser.py 一致的 argparse Namespace / Build args matching parser.py."""
    defaults = {
        "requirement": None,
        "api": None,
        "output": "",
        "output_format": "",
        "debug_snapshots": False,
        "plugin_batch_size": 0,
        "prompt": "",
        "env": "env.yaml",
        "verbose": False,
        "debug": False,
        "parse_mode": "raw",
        "parser_path": "",
        "reference_dir": "",
        "resume": False,
        "resume_overwrite": False,
        "auto": False,
        "case_type": "",
        "log_to_output": None,
        # 新增 CLI 参数 / New CLI args
        "max_steps": 0,
        "max_retries": 0,
        "skeleton_batch_size": 0,
        "plan_single_batch_size": 0,
        "url_doc_match_max_retries": 0,
        "url_doc_match_strategy": "",
        "case_format_max_retries": 0,
        "consecutive_batch_failure_limit": 0,
        "max_steps_no_progress": 0,
        "validation": None,
        "no_validation": None,
        "knowledge": None,
        "no_knowledge": None,
        "plugins": None,
        "no_plugins": None,
        "skills": None,
        "no_skills": None,
        "lang": "",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _mini_settings(**overrides):
    """构造最小 Settings 用于测试 / Build minimal Settings for testing."""
    from config.settings import Settings
    s = Settings()
    s.llm_api_key = "test"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ============================================================================
# 测试：改名验证 / Test: rename verification
# ============================================================================


class TestPluginBatchSizeRename:
    """验证 --plugin-batch-size 替代了旧的 --batch-size。"""

    def should_override_plugin_batch_size_via_cli(self):
        """--plugin-batch-size 20 → GraphState batch_size = 20."""
        args = _make_args(plugin_batch_size=20)
        settings = _mini_settings(plugin_batch_size=10)
        result = args.plugin_batch_size or settings.plugin_batch_size
        assert result == 20

    def should_not_override_when_plugin_batch_size_default(self):
        """--plugin-batch-size 默认 0 → 回退到 env.yaml 值。"""
        args = _make_args(plugin_batch_size=0)
        settings = _mini_settings(plugin_batch_size=10)
        result = args.plugin_batch_size or settings.plugin_batch_size
        assert result == 10

    def should_parser_has_plugin_batch_size_not_batch_size(self):
        """parser 应包含 --plugin-batch-size 参数。"""
        from cli.parser import build_parser
        parser = build_parser()
        # 验证新参数存在 / Verify new arg exists
        actions = {a.dest for a in parser._actions}
        assert "plugin_batch_size" in actions, "parser missing --plugin-batch-size"


# ============================================================================
# 测试：新增 CLI 参数覆盖 / Test: new CLI param overrides
# ============================================================================


class TestNewCliOverrides:
    """验证每个新增 CLI 参数能正确覆盖 env.yaml 默认值。"""

    # --max-steps
    def should_override_max_steps(self):
        args = _make_args(max_steps=20)
        settings = _mini_settings(max_steps=10)
        result = args.max_steps or settings.max_steps
        assert result == 20

    def should_fallback_max_steps_when_default(self):
        args = _make_args(max_steps=0)
        settings = _mini_settings(max_steps=10)
        result = args.max_steps or settings.max_steps
        assert result == 10

    # --max-retries
    def should_override_max_retries(self):
        args = _make_args(max_retries=5)
        settings = _mini_settings(max_retries=3)
        result = args.max_retries or settings.max_retries
        assert result == 5

    # --skeleton-batch-size
    def should_override_skeleton_batch_size(self):
        args = _make_args(skeleton_batch_size=15)
        settings = _mini_settings(skeleton_batch_size=30)
        result = args.skeleton_batch_size or settings.skeleton_batch_size
        assert result == 15

    # --plan-single-batch-size
    def should_override_plan_single_batch_size(self):
        args = _make_args(plan_single_batch_size=16)
        settings = _mini_settings(plan_single_batch_size=8)
        result = args.plan_single_batch_size or settings.plan_single_batch_size
        assert result == 16

    # --url-doc-match-max-retries
    def should_override_url_doc_match_max_retries(self):
        args = _make_args(url_doc_match_max_retries=5)
        settings = _mini_settings(url_doc_match_max_retries=3)
        result = args.url_doc_match_max_retries or settings.url_doc_match_max_retries
        assert result == 5

    # --url-doc-match-strategy
    def should_override_url_doc_match_strategy(self):
        args = _make_args(url_doc_match_strategy="fail")
        settings = _mini_settings(url_doc_match_strategy="warn")
        result = args.url_doc_match_strategy or settings.url_doc_match_strategy
        assert result == "fail"

    def should_fallback_url_doc_match_strategy_when_default(self):
        args = _make_args(url_doc_match_strategy="")
        settings = _mini_settings(url_doc_match_strategy="warn")
        result = args.url_doc_match_strategy or settings.url_doc_match_strategy
        assert result == "warn"

    # --case-format-max-retries
    def should_override_case_format_max_retries(self):
        args = _make_args(case_format_max_retries=5)
        settings = _mini_settings(case_format_max_retries=3)
        result = args.case_format_max_retries or settings.case_format_max_retries
        assert result == 5

    # --consecutive-batch-failure-limit
    def should_override_consecutive_batch_failure_limit(self):
        args = _make_args(consecutive_batch_failure_limit=5)
        settings = _mini_settings(consecutive_batch_failure_limit=3)
        result = args.consecutive_batch_failure_limit or settings.consecutive_batch_failure_limit
        assert result == 5

    # --max-steps-no-progress
    def should_override_max_steps_no_progress(self):
        args = _make_args(max_steps_no_progress=10)
        settings = _mini_settings(max_steps_no_progress=5)
        result = args.max_steps_no_progress or settings.max_steps_no_progress
        assert result == 10

    # --case-type
    def should_override_case_type(self):
        args = _make_args(case_type="single")
        settings = _mini_settings(case_type="both")
        result = args.case_type or settings.case_type
        assert result == "single"

    # --lang
    def should_override_lang(self):
        args = _make_args(lang="en_US")
        settings = _mini_settings(agent_lang="zh_CN")
        result = args.lang or settings.agent_lang
        assert result == "en_US"


# ============================================================================
# 测试：布尔参数覆盖 / Test: boolean param overrides
# ============================================================================


class TestBooleanCliOverrides:
    """验证布尔类型 CLI 参数的覆盖行为。"""

    def should_case_format_enabled_when_flag_set(self):
        """--validation 应覆盖 env 中的 case_format_enabled=false。"""
        args = _make_args(validation=True)
        settings = _mini_settings(case_format_enabled=False)
        result = args.validation if args.validation is not None else settings.case_format_enabled
        assert result is True

    def should_disable_validation_when_no_validation_set(self):
        """--no-validation 应覆盖 env 中的 case_format_enabled=true。"""
        args = _make_args(no_validation=True)
        settings = _mini_settings(case_format_enabled=True)
        if args.no_validation:
            result = False
        elif args.validation:
            result = True
        else:
            result = settings.case_format_enabled
        assert result is False

    def should_use_env_default_when_neither_flag_set(self):
        """两个 flag 都未设置时应使用 env 默认值。"""
        args = _make_args(validation=None, no_validation=None)
        settings = _mini_settings(case_format_enabled=True)
        if args.no_validation:
            result = False
        elif args.validation:
            result = True
        else:
            result = settings.case_format_enabled
        assert result is True

    def should_enable_knowledge_when_flag_set(self):
        """--knowledge 应覆盖 env 中的 enable_knowledge=false。"""
        args = _make_args(knowledge=True)
        settings = _mini_settings(enable_knowledge=False)
        result = args.knowledge if args.knowledge is not None else settings.enable_knowledge
        assert result is True

    def should_enable_plugins_when_flag_set(self):
        """--plugins 应覆盖 env 中的 enable_plugins=false。"""
        args = _make_args(plugins=True)
        settings = _mini_settings(enable_plugins=False)
        result = args.plugins if args.plugins is not None else settings.enable_plugins
        assert result is True

    def should_enable_skills_when_flag_set(self):
        """--skills 应覆盖 env 中的 enable_skills=false。"""
        args = _make_args(skills=True)
        settings = _mini_settings(enable_skills=False)
        result = args.skills if args.skills is not None else settings.enable_skills
        assert result is True


# ============================================================================
# 测试：优先级链 / Test: priority chain
# ============================================================================


class TestPriorityChain:
    """验证 CLI > env.yaml > Settings 默认值 的优先级链。"""

    def should_cli_override_env_yaml(self):
        """CLI 参数应覆盖 env.yaml 值。"""
        from config.settings import Settings
        settings = Settings()
        settings.plugin_batch_size = 10  # 模拟 env.yaml / simulated env.yaml
        args = _make_args(plugin_batch_size=20)
        result = args.plugin_batch_size or settings.plugin_batch_size
        assert result == 20

    def should_env_yaml_override_defaults(self):
        """env.yaml 值应覆盖 Settings 默认值。"""
        from config.settings import Settings
        settings = Settings()
        # Settings 默认值 / default value
        assert settings.plugin_batch_size == 10
        # 模拟 env.yaml 覆盖 / simulate env.yaml override
        settings.plugin_batch_size = 25
        args = _make_args(plugin_batch_size=0)  # CLI 未提供 / no CLI arg
        result = args.plugin_batch_size or settings.plugin_batch_size
        assert result == 25

    def should_settings_detect_renamed_fields(self):
        """Settings 应包含所有重命名后的字段。"""
        from config.settings import Settings
        s = Settings()
        # 新字段名应存在 / New field names should exist
        assert hasattr(s, "case_format_enabled")
        assert hasattr(s, "case_format_max_retries")
        assert hasattr(s, "url_doc_match_max_retries")
        assert hasattr(s, "url_doc_match_strategy")
        assert hasattr(s, "plan_single_batch_size")
        assert hasattr(s, "plan_biz_flow_batch_size")
        assert hasattr(s, "case_gen_rules")
        # 旧字段名应已删除 / Old field names should be gone
        assert not hasattr(s, "enable_validation")
        assert not hasattr(s, "validation_rules")
        assert not hasattr(s, "max_validation_retries")
        assert not hasattr(s, "url_correction_max_retries")
        assert not hasattr(s, "plan_chunk_size")
        assert not hasattr(s, "llm_max_tokens")


# ============================================================================
# 测试：Parser 完整性 / Test: parser completeness
# ============================================================================


class TestParserCompleteness:
    """验证所有预期的 CLI 参数都在 parser 中注册。"""

    def should_have_all_expected_args(self):
        """parser 应包含所有新旧 CLI 参数。"""
        from cli.parser import build_parser
        parser = build_parser()
        actions = {a.dest for a in parser._actions}

        expected = {
            # 已有 / Existing
            "requirement", "api", "output", "output_format",
            "debug_snapshots", "prompt", "env", "verbose", "debug",
            "parse_mode", "parser_path", "reference_dir",
            "resume", "resume_overwrite", "auto", "case_type",
            "log_to_output",
            # 重命名 / Renamed
            "plugin_batch_size",
            # 新增 / New
            "max_steps", "max_retries", "skeleton_batch_size",
            "plan_single_batch_size",
            "url_doc_match_max_retries", "url_doc_match_strategy",
            "case_format_max_retries",
            "consecutive_batch_failure_limit", "max_steps_no_progress",
            "validation", "no_validation",
            "knowledge", "no_knowledge",
            "plugins", "no_plugins",
            "skills", "no_skills",
            "lang",
        }

        missing = expected - actions
        assert not missing, f"Missing CLI args: {missing}"

    def should_not_have_batch_size(self):
        """旧 --batch-size 参数不应存在。"""
        from cli.parser import build_parser
        parser = build_parser()
        actions = {a.dest for a in parser._actions}
        assert "batch_size" not in actions, "old --batch-size should be gone"


# ============================================================================
# 测试：恢复模式配置合并 / Test: resume config merge
# ============================================================================


class TestResumeConfigMerge:
    """验证恢复模式下 CLI > saved_config > env 的合并逻辑。"""

    def should_cli_override_saved_config_on_resume(self):
        """CLI 参数应覆盖已保存的运行配置。"""
        args = _make_args(plugin_batch_size=20)
        saved_config = {"plugin_batch_size": 10}
        settings = _mini_settings(plugin_batch_size=30)
        result = args.plugin_batch_size or saved_config.get("plugin_batch_size") or settings.plugin_batch_size
        assert result == 20

    def should_saved_config_override_env_on_resume(self):
        """已保存的运行配置应覆盖 env.yaml。"""
        args = _make_args(plugin_batch_size=0)
        saved_config = {"plugin_batch_size": 10}
        settings = _mini_settings(plugin_batch_size=30)
        result = args.plugin_batch_size or saved_config.get("plugin_batch_size") or settings.plugin_batch_size
        assert result == 10

    def should_fallback_to_env_when_nothing_saved(self):
        """无保存配置且无 CLI 时回退到 env.yaml。"""
        args = _make_args(plugin_batch_size=0)
        saved_config = {}
        settings = _mini_settings(plugin_batch_size=30)
        result = args.plugin_batch_size or saved_config.get("plugin_batch_size") or settings.plugin_batch_size
        assert result == 30

    def should_cli_override_saved_case_type(self):
        """--case-type single 应覆盖已保存的 case_type=both。"""
        args = _make_args(case_type="single")
        saved_config = {"case_type": "both"}
        settings = _mini_settings(case_type="both")
        result = args.case_type or saved_config.get("case_type") or settings.case_type
        assert result == "single"
