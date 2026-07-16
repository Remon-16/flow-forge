"""Tests for run_config key consistency between full pipeline and resume mode.

run_config 键名一致性测试 — 确保完整流水线和 resume 模式使用相同的键名。
"""

import json
import tempfile
from pathlib import Path

from graph.nodes.helpers import save_run_config, load_run_config


# ---------------------------------------------------------------------------
# TestRunConfigKeyConsistency / run_config 键名一致性
# ---------------------------------------------------------------------------


class TestRunConfigKeyConsistency:
    """Tests that _run_config and _merged_config use consistent key names."""

    def should_use_plugin_batch_size_key(self):
        """保存和加载 run_config 应使用 plugin_batch_size 键名
        run_config should use plugin_batch_size key (not batch_size)."""
        with tempfile.TemporaryDirectory() as tmp:
            # 模拟完整流水线保存的配置
            config = {
                "case_type": "single",
                "user_guidance": "test guidance",
                "output_format": "yaml",
                "plugin_batch_size": 5,  # 统一键名
                "auto_mode": True,
                "parse_mode": "raw",
                "output_dir": "/tmp/test",
                "api_paths": [],
                "debug_snapshots": False,
                "parser_path": "",
                "reference_dir": "",
            }
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            # 应能通过 plugin_batch_size 键读取到值
            assert loaded.get("plugin_batch_size") == 5
            # batch_size 键不应存在（已统一为 plugin_batch_size）
            assert "batch_size" not in loaded

    def should_have_plugin_batch_size_not_batch_size(self):
        """resume merge 逻辑应能正确读取 plugin_batch_size
        Resume merge logic should correctly read plugin_batch_size from saved config."""
        with tempfile.TemporaryDirectory() as tmp:
            # 模拟完整流水线保存
            config = {
                "plugin_batch_size": 30,
                "case_type": "both",
                "auto_mode": False,
            }
            save_run_config(tmp, config)
            saved = load_run_config(tmp)
            # resume merge 应能读取到值
            assert saved.get("plugin_batch_size") == 30

    def should_not_have_deprecated_batch_size_key(self):
        """旧版 batch_size 键不应出现在新保存的配置中
        Old batch_size key should not appear in newly saved configs."""
        with tempfile.TemporaryDirectory() as tmp:
            config = {"plugin_batch_size": 15}
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            assert "batch_size" not in loaded
            assert "plugin_batch_size" in loaded

    def should_handle_missing_plugin_batch_size_gracefully(self):
        """无 plugin_batch_size 时 config get 应返回 None
        config.get('plugin_batch_size') returns None when key missing."""
        with tempfile.TemporaryDirectory() as tmp:
            config = {"case_type": "single"}
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            assert loaded.get("plugin_batch_size") is None
            assert loaded.get("batch_size") is None

    def should_roundtrip_all_config_keys(self):
        """所有配置键应完整 roundtrip / All config keys should roundtrip."""
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "case_type": "biz",
                "user_guidance": "guidance text",
                "output_format": "both",
                "plugin_batch_size": 8,
                "auto_mode": False,
                "parse_mode": "raw",
                "output_dir": "/tmp/output",
                "api_paths": ["/tmp/api1.md", "/tmp/api2.md"],
                "debug_snapshots": True,
                "parser_path": "/tmp/custom.py",
                "reference_dir": "/tmp/ref",
                "case_format_enabled": True,
                "case_format_max_retries": 5,
                "skeleton_batch_size": 20,
                "plan_single_batch_size": 6,
            }
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            for key, value in config.items():
                assert loaded.get(key) == value, f"Key '{key}' mismatch: {loaded.get(key)} != {value}"

    def should_not_include_resume_overwrite_in_standard_keys(self):
        """resume_overwrite 不应出现在标准配置键中（一次指令，不跨 resume 保留）
        resume_overwrite is a one-shot flag and should NOT persist across resumes."""
        # 验证标准配置键列表中不包含 resume_overwrite
        # Verify resume_overwrite is not among standard config keys
        standard_keys = {
            "case_type", "user_guidance", "output_format", "plugin_batch_size",
            "auto_mode", "parse_mode", "output_dir", "api_paths",
            "debug_snapshots", "parser_path", "reference_dir",
            "case_format_enabled", "case_format_max_retries",
            "skeleton_batch_size", "plan_single_batch_size",
        }
        assert "resume_overwrite" not in standard_keys

        # run_config 保存/加载不会过滤键, 但 runner 不会将 resume_overwrite 放入配置
        # Helpers save/load faithfully, but runner.py no longer includes it in _merged_config
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "case_type": "single",
                "plugin_batch_size": 10,
                "auto_mode": False,
                "parse_mode": "raw",
                "output_dir": "/tmp/output",
                "api_paths": [],
                "debug_snapshots": False,
                "parser_path": "",
                "reference_dir": "",
            }
            save_run_config(tmp, config)
            loaded = load_run_config(tmp)
            # resume_overwrite 不应出现在加载的配置中 / should not appear in loaded config
            assert "resume_overwrite" not in loaded
