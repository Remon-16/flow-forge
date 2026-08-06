"""Tests for config helpers — _ensure_list 类型规范化。
Tests for config helpers — _ensure_list type normalization.
"""

import pytest

from config.settings import _ensure_list


class TestEnsureList:
    """测试 _ensure_list 字符串→列表规范化。
    Test _ensure_list string→list normalization.
    """

    # ------------------------------------------------------------------
    # 字符串 → 单元素列表 / string → single-element list
    # ------------------------------------------------------------------

    def test_ensure_list_string_to_list(self):
        """字符串输入应被包裹为单元素列表。
        String input should be wrapped in a single-element list.
        """
        assert _ensure_list("plugins.official.Foo") == ["plugins.official.Foo"]
        assert _ensure_list("a.b.Class") == ["a.b.Class"]

    def test_ensure_list_empty_string(self):
        """空字符串仍被包裹为列表（由消费端 strip 过滤）。
        Empty string still gets wrapped as list (consumer strips/filters).
        """
        assert _ensure_list("") == [""]

    # ------------------------------------------------------------------
    # 列表 → 保持不变 / list → unchanged
    # ------------------------------------------------------------------

    def test_ensure_list_list_unchanged(self):
        """列表输入应保持不变。
        List input should remain unchanged.
        """
        assert _ensure_list(["a.b.Class"]) == ["a.b.Class"]
        assert _ensure_list(["a.b.Class", "c.d.Class"]) == ["a.b.Class", "c.d.Class"]

    def test_ensure_list_empty_list(self):
        """空列表应保持不变。
        Empty list should remain unchanged.
        """
        assert _ensure_list([]) == []

    # ------------------------------------------------------------------
    # 其他类型 → 空列表 / other types → empty list
    # ------------------------------------------------------------------

    def test_ensure_list_none(self):
        """None 输入 → 空列表（防御性处理）。
        None input → empty list (defensive handling).
        """
        assert _ensure_list(None) == []

    def test_ensure_list_dict(self):
        """dict 输入 → 空列表（防御性处理）。
        dict input → empty list (defensive handling).
        """
        assert _ensure_list({"key": "val"}) == []

    def test_ensure_list_int(self):
        """int 输入 → 空列表（防御性处理）。
        int input → empty list (defensive handling).
        """
        assert _ensure_list(42) == []
