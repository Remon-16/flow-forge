"""Tests for _arg_kwargs — 验证 schema action 键被正确传递给 argparse。
Tests for _arg_kwargs — verify schema action key is correctly passed to argparse.
"""

import argparse
import sys

import pytest

# 确保可以导入 flow_forge_schemas / Ensure flow_forge_schemas is importable
sys.path.insert(0, "..")

from flow_forge_schemas.cli import _arg_kwargs


class TestArgKwargsActionPassthrough:
    """测试 _arg_kwargs 对 action 键的处理。
    Test _arg_kwargs handling of the action key.
    """

    # ------------------------------------------------------------------
    # str + append — 核心修复验证 / core fix verification
    # ------------------------------------------------------------------

    def test_action_append_passed_to_kwargs(self):
        """str 类型带 action: "append" → kwargs 应包含 action: "append"。
        str type with action: "append" → kwargs should include action: "append".
        """
        arg = {"type": "str", "action": "append", "default": None}
        kwargs = _arg_kwargs(arg)
        assert kwargs["action"] == "append"
        assert kwargs["type"] == str

    def test_action_append_produces_list_in_argparse(self):
        """完整流程：str + append + default null → argparse 正确返回列表。
        Full flow: str + append + default null → argparse correctly returns list.
        """
        arg = {"type": "str", "action": "append", "default": None}
        kwargs = _arg_kwargs(arg)
        # 验证 kwargs 中没有 default=None（null default 不应传递给 argparse）
        # Verify default=None is not passed to argparse (null default omitted)
        assert "default" not in kwargs

        parser = argparse.ArgumentParser()
        parser.add_argument("--test", **kwargs)
        # 不传参：应为 None / Not passed: should be None
        result = parser.parse_args([])
        assert result.test is None
        # 传一次：应为列表 / Passed once: should be list
        result = parser.parse_args(["--test", "a.b.Class"])
        assert result.test == ["a.b.Class"]
        # 传多次 / Passed multiple times
        result = parser.parse_args([
            "--test", "a.b.Class",
            "--test", "c.d.Class",
        ])
        assert result.test == ["a.b.Class", "c.d.Class"]

    # ------------------------------------------------------------------
    # bool_store_true — action 不应被覆盖 / action should not be overwritten
    # ------------------------------------------------------------------

    def test_action_store_true_not_overwritten(self):
        """bool_store_true 类型应该保持 action: "store_true"，不被覆盖。
        bool_store_true type should keep action: "store_true", not overwritten.
        """
        arg = {"type": "bool_store_true", "action": "append"}
        kwargs = _arg_kwargs(arg)
        assert kwargs["action"] == "store_true"

    def test_action_store_false_not_overwritten(self):
        """bool_store_false 类型应该保持 action: "store_false"。
        bool_store_false type should keep action: "store_false".
        """
        arg = {"type": "bool_store_false", "action": "append"}
        kwargs = _arg_kwargs(arg)
        assert kwargs["action"] == "store_false"

    # ------------------------------------------------------------------
    # 无 action — kwargs 不应含 action 键 / no action — kwargs should have no action key
    # ------------------------------------------------------------------

    def test_action_not_in_schema_not_in_kwargs(self):
        """schema 不含 action → kwargs 不应有 action 键（除 bool 类型外）。
        Schema without action → kwargs should not have action key (except bool types).
        """
        arg = {"type": "str", "default": "hello"}
        kwargs = _arg_kwargs(arg)
        assert "action" not in kwargs

    def test_int_type_no_action(self):
        """int 类型不含 action → kwargs 不应有 action 键。
        int type without action → kwargs should not have action key.
        """
        arg = {"type": "int", "default": 42}
        kwargs = _arg_kwargs(arg)
        assert "action" not in kwargs
        assert kwargs["type"] == int

    def test_float_type_no_action(self):
        """float 类型不含 action → kwargs 不应有 action 键。
        float type without action → kwargs should not have action key.
        """
        arg = {"type": "float", "default": 3.14}
        kwargs = _arg_kwargs(arg)
        assert "action" not in kwargs
        assert kwargs["type"] == float

    # ------------------------------------------------------------------
    # 其他 kwargs 键 — 确保未受影响 / other kwargs keys — ensure unaffected
    # ------------------------------------------------------------------

    def test_nargs_still_passed(self):
        """nargs 键仍被正确传递。
        nargs key is still passed correctly.
        """
        arg = {"type": "str", "nargs": 2}
        kwargs = _arg_kwargs(arg)
        assert kwargs["nargs"] == 2

    def test_choices_still_passed(self):
        """choices 键仍被正确传递。
        choices key is still passed correctly.
        """
        arg = {"type": "str", "choices": ["a", "b"]}
        kwargs = _arg_kwargs(arg)
        assert kwargs["choices"] == ["a", "b"]

    def test_required_still_passed(self):
        """required 键仍被正确传递。
        required key is still passed correctly.
        """
        arg = {"type": "str", "required": True}
        kwargs = _arg_kwargs(arg)
        assert kwargs["required"] is True
