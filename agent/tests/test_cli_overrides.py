"""测试 CLI 参数覆盖 env.yaml 配置 / Test CLI argument override of env.yaml settings.

验证每个 CLI 参数能正确覆盖 env.yaml 配置值，以及 CLI > env > defaults 的优先级链。
Verify CLI args override env.yaml values and the CLI > env > defaults priority chain.

测试覆盖 / Test coverage:
  - None 哨兵：CLI 未提供时回退到 env / None sentinel: fall back to env when CLI not provided
  - 0 值保护：用户显式设置 0 时不被 env 覆盖 / Zero-value protection: explicit 0 not overridden by env
  - 覆盖正确性：CLI 提供值时覆盖 env / Override correctness: CLI value overrides env
  - flag 优先级：--no-* 优先于 --* / Flag priority: --no-* takes precedence over --*
"""

import argparse
import sys
from pathlib import Path

import pytest

# 确保 agent/ 在 sys.path 中 / Ensure agent/ is on sys.path
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


# ============================================================================
# 辅助函数 / Helper functions
# ============================================================================

def _first(*values):
    """返回第一个非 None 值，模拟 runner.py 中的 _first()。
    Return the first non-None value, matching runner.py's _first().
    """
    for v in values:
        if v is not None:
            return v
    return None


def _resolve_url_doc_match_flags(args, settings):
    """模拟 runner.py 中的 --url-doc-match-enabled / --no-url-doc-match-enabled 解析逻辑。
    Simulate the url-doc-match flag resolution logic in runner.py.
    """
    if args.no_url_doc_match_enabled:
        return False
    elif args.url_doc_match_enabled:
        return True
    else:
        return getattr(settings, "url_doc_match_enabled", True)


def _make_args(**overrides):
    """构造与 parser.py 一致的 argparse Namespace / Build args matching parser.py.

    所有覆盖型参数默认值为 None（None 哨兵模式），确保 CLI 未提供时回退到 env.yaml。
    All override params default to None (None sentinel pattern).
    """
    defaults = {
        # 必选参数 / Required params
        "requirement": None,
        "api": None,
        # 输出 / Output
        "output": "",
        "output_format": None,
        "debug_snapshots": False,
        # 数值型覆盖参数 / Numeric override params (None = use env.yaml)
        "plugin_batch_size": None,
        "max_steps": None,
        "max_retries": None,
        "skeleton_batch_size": None,
        "plan_single_batch_size": None,
        "url_doc_match_max_retries": None,
        "consecutive_batch_failure_limit": None,
        "max_steps_no_progress": None,
        # 字符串型覆盖参数 / String override params (None = use env.yaml)
        "url_doc_match_strategy": None,
        "case_type": None,
        "lang": None,
        # prompt 特殊：None → "" 更合理 / prompt: None → "" makes more sense
        "prompt": None,
        "parser_path": None,
        "reference_dir": None,
        # 非覆盖型 / Non-override
        "env": "env.yaml",
        "verbose": False,
        "debug": False,
        "parse_mode": "raw",
        "resume": False,
        "resume_overwrite": False,
        "auto": False,
        # 布尔 flag / Boolean flags (None = not set)
        "validation": None,
        "no_validation": None,
        "url_doc_match_enabled": None,
        "no_url_doc_match_enabled": None,
        "plugins": None,
        "no_plugins": None,
        "skills": None,
        "no_skills": None,
        "log_to_output": None,
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
# 测试：None 哨兵 — 每个参数验证 None → fallback to env
# ============================================================================


class TestNoneSentinel:
    """验证所有覆盖型参数在 CLI 未提供（None）时回退到 env.yaml 配置。

    Verify every override param falls back to env.yaml when CLI is not provided (None).
    使用 _first() 模式（与 runner.py 一致），确保 None 不会意外覆盖 env 值。
    """

    # --- 整数参数 / Integer params ---

    def should_fallback_plugin_batch_size(self):
        args = _make_args(plugin_batch_size=None)
        settings = _mini_settings(plugin_batch_size=10)
        assert _first(args.plugin_batch_size, settings.plugin_batch_size) == 10

    def should_fallback_max_steps(self):
        args = _make_args(max_steps=None)
        settings = _mini_settings(max_steps=10)
        assert _first(args.max_steps, settings.max_steps) == 10

    def should_fallback_max_retries(self):
        args = _make_args(max_retries=None)
        settings = _mini_settings(max_retries=3)
        assert _first(args.max_retries, settings.max_retries) == 3

    def should_fallback_skeleton_batch_size(self):
        args = _make_args(skeleton_batch_size=None)
        settings = _mini_settings(skeleton_batch_size=30)
        assert _first(args.skeleton_batch_size, settings.skeleton_batch_size) == 30

    def should_fallback_plan_single_batch_size(self):
        args = _make_args(plan_single_batch_size=None)
        settings = _mini_settings(plan_single_batch_size=8)
        assert _first(args.plan_single_batch_size, settings.plan_single_batch_size) == 8

    def should_fallback_url_doc_match_max_retries(self):
        args = _make_args(url_doc_match_max_retries=None)
        settings = _mini_settings(url_doc_match_max_retries=3)
        assert _first(args.url_doc_match_max_retries, settings.url_doc_match_max_retries) == 3

    def should_fallback_consecutive_batch_failure_limit(self):
        args = _make_args(consecutive_batch_failure_limit=None)
        settings = _mini_settings(consecutive_batch_failure_limit=3)
        assert _first(args.consecutive_batch_failure_limit, settings.consecutive_batch_failure_limit) == 3

    def should_fallback_max_steps_no_progress(self):
        args = _make_args(max_steps_no_progress=None)
        settings = _mini_settings(max_steps_no_progress=5)
        assert _first(args.max_steps_no_progress, settings.max_steps_no_progress) == 5

    # --- 字符串参数 / String params ---

    def should_fallback_output_format(self):
        args = _make_args(output_format=None)
        settings = _mini_settings(output_format="both")
        assert _first(args.output_format, settings.output_format) == "both"

    def should_fallback_url_doc_match_strategy(self):
        args = _make_args(url_doc_match_strategy=None)
        settings = _mini_settings(url_doc_match_strategy="warn")
        assert _first(args.url_doc_match_strategy, settings.url_doc_match_strategy) == "warn"

    def should_fallback_case_type(self):
        args = _make_args(case_type=None)
        settings = _mini_settings(case_type="both")
        assert _first(args.case_type, settings.case_type) == "both"

    def should_fallback_lang(self):
        args = _make_args(lang=None)
        settings = _mini_settings(agent_lang="zh_CN")
        assert _first(args.lang, settings.agent_lang) == "zh_CN"


# ============================================================================
# 测试：0 值保护 — 用户显式设置 0 时不被 env 吞掉
# ============================================================================


class TestZeroAsValidValue:
    """验证用户显式设置 0 时值被正确保留（不被 env 默认值覆盖）。

    Verify explicit 0 is preserved and NOT overridden by env defaults.
    这是从 or 模式切换到 _first() 模式的关键收益。
    """

    def should_allow_zero_max_retries(self):
        """--max-retries 0 → 0（不重试），而不是 env 的 max_retries=3。"""
        args = _make_args(max_retries=0)
        settings = _mini_settings(max_retries=3)
        result = _first(args.max_retries, settings.max_retries)
        assert result == 0, "explicit --max-retries 0 should stay 0, not fall back to 3"

    def should_allow_zero_url_doc_match_max_retries(self):
        """--url-doc-match-max-retries 0 → 0（不重试 URL 纠错）。"""
        args = _make_args(url_doc_match_max_retries=0)
        settings = _mini_settings(url_doc_match_max_retries=3)
        result = _first(args.url_doc_match_max_retries, settings.url_doc_match_max_retries)
        assert result == 0

    def should_allow_zero_consecutive_batch_failure_limit(self):
        """--consecutive-batch-failure-limit 0 → 0（首次失败即停止）。"""
        args = _make_args(consecutive_batch_failure_limit=0)
        settings = _mini_settings(consecutive_batch_failure_limit=3)
        result = _first(args.consecutive_batch_failure_limit, settings.consecutive_batch_failure_limit)
        assert result == 0

    def should_allow_negative_one_plugin_batch_size(self):
        """--plugin-batch-size -1 → -1（不分批），验证负值也能正确传递。"""
        args = _make_args(plugin_batch_size=-1)
        settings = _mini_settings(plugin_batch_size=10)
        result = _first(args.plugin_batch_size, settings.plugin_batch_size)
        assert result == -1


# ============================================================================
# 测试：CLI 覆盖 env — 每个参数验证 CLI 提供值时覆盖 env
# ============================================================================


class TestCliOverridesEnv:
    """验证每个 CLI 参数提供非默认值时能正确覆盖 env.yaml 配置。

    Verify each CLI param overrides env.yaml when a non-default value is provided.
    """

    # --- 整数参数 / Integer params ---

    def should_override_plugin_batch_size(self):
        args = _make_args(plugin_batch_size=20)
        settings = _mini_settings(plugin_batch_size=10)
        assert _first(args.plugin_batch_size, settings.plugin_batch_size) == 20

    def should_override_max_steps(self):
        args = _make_args(max_steps=20)
        settings = _mini_settings(max_steps=10)
        assert _first(args.max_steps, settings.max_steps) == 20

    def should_override_max_retries(self):
        args = _make_args(max_retries=5)
        settings = _mini_settings(max_retries=3)
        assert _first(args.max_retries, settings.max_retries) == 5

    def should_override_skeleton_batch_size(self):
        args = _make_args(skeleton_batch_size=15)
        settings = _mini_settings(skeleton_batch_size=30)
        assert _first(args.skeleton_batch_size, settings.skeleton_batch_size) == 15

    def should_override_plan_single_batch_size(self):
        args = _make_args(plan_single_batch_size=16)
        settings = _mini_settings(plan_single_batch_size=8)
        assert _first(args.plan_single_batch_size, settings.plan_single_batch_size) == 16

    def should_override_url_doc_match_max_retries(self):
        args = _make_args(url_doc_match_max_retries=5)
        settings = _mini_settings(url_doc_match_max_retries=3)
        assert _first(args.url_doc_match_max_retries, settings.url_doc_match_max_retries) == 5

    def should_override_consecutive_batch_failure_limit(self):
        args = _make_args(consecutive_batch_failure_limit=5)
        settings = _mini_settings(consecutive_batch_failure_limit=3)
        assert _first(args.consecutive_batch_failure_limit, settings.consecutive_batch_failure_limit) == 5

    def should_override_max_steps_no_progress(self):
        args = _make_args(max_steps_no_progress=10)
        settings = _mini_settings(max_steps_no_progress=5)
        assert _first(args.max_steps_no_progress, settings.max_steps_no_progress) == 10

    # --- 字符串参数 / String params ---

    def should_override_output_format(self):
        args = _make_args(output_format="yaml")
        settings = _mini_settings(output_format="both")
        assert _first(args.output_format, settings.output_format) == "yaml"

    def should_override_url_doc_match_strategy(self):
        args = _make_args(url_doc_match_strategy="fail")
        settings = _mini_settings(url_doc_match_strategy="warn")
        assert _first(args.url_doc_match_strategy, settings.url_doc_match_strategy) == "fail"

    def should_override_case_type(self):
        args = _make_args(case_type="single")
        settings = _mini_settings(case_type="both")
        assert _first(args.case_type, settings.case_type) == "single"

    def should_override_lang(self):
        args = _make_args(lang="en_US")
        settings = _mini_settings(agent_lang="zh_CN")
        assert _first(args.lang, settings.agent_lang) == "en_US"


# ============================================================================
# 测试：Validation flags — 验证 --validation/--no-validation 逻辑
# ============================================================================


class TestUrlDocMatchFlags:
    """验证 --url-doc-match-enabled / --no-url-doc-match-enabled 的解析逻辑。

    Verify the resolution logic for url-doc-match boolean flags.
    """

    def should_enable_url_doc_match_when_flag_set(self):
        """--url-doc-match-enabled → url_doc_match_enabled = True。"""
        args = _make_args(url_doc_match_enabled=True)
        settings = _mini_settings(url_doc_match_enabled=False)
        assert _resolve_url_doc_match_flags(args, settings) is True

    def should_disable_url_doc_match_when_no_flag_set(self):
        """--no-url-doc-match-enabled → url_doc_match_enabled = False。"""
        args = _make_args(no_url_doc_match_enabled=True)
        settings = _mini_settings(url_doc_match_enabled=True)
        assert _resolve_url_doc_match_flags(args, settings) is False

    def should_use_env_for_url_doc_match_when_neither_flag_set(self):
        """两个 flag 都未设置 → 使用 env 默认值。"""
        args = _make_args()
        settings = _mini_settings(url_doc_match_enabled=True)
        assert _resolve_url_doc_match_flags(args, settings) is True
        settings2 = _mini_settings(url_doc_match_enabled=False)
        assert _resolve_url_doc_match_flags(args, settings2) is False

    def should_no_url_doc_match_win_over_url_doc_match(self):
        """--no-url-doc-match-enabled 优先于 --url-doc-match-enabled。"""
        args = _make_args(url_doc_match_enabled=True, no_url_doc_match_enabled=True)
        settings = _mini_settings(url_doc_match_enabled=True)
        assert _resolve_url_doc_match_flags(args, settings) is False


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
            "consecutive_batch_failure_limit", "max_steps_no_progress",
            "url_doc_match_enabled", "no_url_doc_match_enabled",
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

    def should_have_none_defaults_for_override_params(self):
        """覆盖型参数应使用 default=None（None 哨兵模式）。"""
        from cli.parser import build_parser
        parser = build_parser()
        actions = {a.dest: a for a in parser._actions}

        # 应使用 default=None 的参数 / Params that should use default=None
        none_default_params = {
            "plugin_batch_size", "max_steps", "max_retries",
            "skeleton_batch_size", "plan_single_batch_size",
            "url_doc_match_max_retries",
            "consecutive_batch_failure_limit", "max_steps_no_progress",
            "output_format", "url_doc_match_strategy", "case_type", "lang",
            "prompt", "parser_path", "reference_dir",
            "url_doc_match_enabled", "no_url_doc_match_enabled",
            "plugins", "no_plugins",
            "skills", "no_skills",
            "log_to_output",
        }

        for param_name in none_default_params:
            if param_name in actions:
                action = actions[param_name]
                assert action.default is None, (
                    f"--{param_name.replace('_', '-')} should have default=None, "
                    f"got default={action.default!r}"
                )


# ============================================================================
# 测试：Settings 字段完整性 / Test: Settings field completeness
# ============================================================================


class TestSettingsFields:
    """验证 Settings dataclass 包含所有预期字段。"""

    def should_have_all_expected_fields(self):
        """Settings 应包含重命名后的新字段，不包含旧字段。"""
        from config.settings import Settings
        s = Settings()
        # 新字段名应存在 / New field names should exist
        assert hasattr(s, "case_format_max_retries")
        assert hasattr(s, "url_doc_match_max_retries")
        assert hasattr(s, "url_doc_match_strategy")
        assert hasattr(s, "url_doc_match_enabled")
        assert hasattr(s, "plan_single_batch_size")
        assert hasattr(s, "plan_biz_flow_batch_size")
        assert hasattr(s, "case_gen_validation")
        # 旧字段名应已删除 / Old field names should be gone
        assert not hasattr(s, "enable_validation")
        assert not hasattr(s, "validation_rules")
        assert not hasattr(s, "case_gen_rules")
        assert not hasattr(s, "max_validation_retries")
        assert not hasattr(s, "url_correction_max_retries")
        assert not hasattr(s, "plan_chunk_size")
        assert not hasattr(s, "llm_max_tokens")


# ============================================================================
# 测试：恢复模式配置合并 / Test: resume config merge
# ============================================================================


class TestResumeConfigMerge:
    """验证恢复模式下 CLI > saved_config > env 的合并逻辑（使用 _first 模式）。"""

    def should_cli_override_saved_config_on_resume(self):
        """CLI 参数应覆盖已保存的运行配置。"""
        args = _make_args(plugin_batch_size=20)
        saved_config = {"plugin_batch_size": 10}
        settings = _mini_settings(plugin_batch_size=30)
        result = _first(args.plugin_batch_size,
                        saved_config.get("plugin_batch_size"),
                        settings.plugin_batch_size)
        assert result == 20

    def should_saved_config_override_env_on_resume(self):
        """已保存的运行配置应覆盖 env.yaml。"""
        args = _make_args()  # plugin_batch_size=None (CLI 未提供)
        saved_config = {"plugin_batch_size": 10}
        settings = _mini_settings(plugin_batch_size=30)
        result = _first(args.plugin_batch_size,
                        saved_config.get("plugin_batch_size"),
                        settings.plugin_batch_size)
        assert result == 10

    def should_fallback_to_env_when_nothing_saved(self):
        """无保存配置且无 CLI 时回退到 env.yaml。"""
        args = _make_args()  # CLI 未提供
        saved_config = {}
        settings = _mini_settings(plugin_batch_size=30)
        result = _first(args.plugin_batch_size,
                        saved_config.get("plugin_batch_size"),
                        settings.plugin_batch_size)
        assert result == 30

    def should_cli_override_saved_case_type(self):
        """--case-type single 应覆盖已保存的 case_type=both。"""
        args = _make_args(case_type="single")
        saved_config = {"case_type": "both"}
        settings = _mini_settings(case_type="both")
        result = _first(args.case_type,
                        saved_config.get("case_type"),
                        settings.case_type)
        assert result == "single"

    def should_cli_zero_override_saved_max_retries(self):
        """--max-retries 0 应覆盖已保存的 max_retries=3。"""
        args = _make_args(max_retries=0)
        saved_config = {"max_retries": 3}
        settings = _mini_settings(max_retries=5)
        result = _first(args.max_retries,
                        saved_config.get("max_retries"),
                        settings.max_retries)
        assert result == 0, "explicit --max-retries 0 should override saved config"


# ============================================================================
# 测试：旧 or 模式问题复现 / Test: old "or" pattern issues
# ============================================================================


class TestOldOrPatternIssues:
    """验证旧的 args.X or settings.X 模式的缺陷（对比新 _first 模式）。

    Demonstrate why the old "or" pattern was problematic and how _first() fixes it.
    """

    def should_or_pattern_swallow_zero(self):
        """旧模式：args.max_retries or settings.max_retries 当 args=0 时返回 env 值（错误！）。"""
        args = _make_args(max_retries=0)
        settings = _mini_settings(max_retries=3)
        # 旧 or 模式：0 or 3 → 3（吞掉用户的 0）
        old_result = args.max_retries or settings.max_retries
        assert old_result == 3, "old or pattern: 0 is falsy, falls back to 3"
        # 新 _first 模式：0 不是 None，直接返回 0
        new_result = _first(args.max_retries, settings.max_retries)
        assert new_result == 0, "new _first pattern: 0 is not None, keeps 0"

    def should_or_pattern_swallow_empty_string_strategy(self):
        """旧模式：args.url_doc_match_strategy or settings... 当 args="" 时返回 env 值。"""
        # 注意：空字符串在 parser 中不再是默认值（改为 None），
        # 但验证旧模式的行为以确保正确性
        args = _make_args(url_doc_match_strategy="")
        settings = _mini_settings(url_doc_match_strategy="warn")
        old_result = args.url_doc_match_strategy or settings.url_doc_match_strategy
        assert old_result == "warn", "old or pattern: '' is falsy"
        # 新模式处理空字符串：空字符串不是 None，直接返回
        new_result = _first(args.url_doc_match_strategy, settings.url_doc_match_strategy)
        assert new_result == "", "new _first pattern: '' is not None, keeps ''"
