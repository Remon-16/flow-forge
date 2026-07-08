"""Tests for review annotation three-phase revision flow.

测试批注修订三阶段流程中的关键函数。
Tests for _build_apply_user_prompt and __global__ annotation handling.
"""

import pytest

from graph.nodes.review_annotation import _build_apply_user_prompt, _map_annotations_to_sections


# ---------------------------------------------------------------------------
# TestBuildApplyUserPrompt / 构建 Phase 3 USER prompt 测试
# ---------------------------------------------------------------------------


class TestBuildApplyUserPrompt:
    """Tests for _build_apply_user_prompt()."""

    def should_use_annotations_not_intent_actions(self):
        """_build_apply_user_prompt 应使用原始批注数据而非意图分析结果。

        Should read selected_text and review_comment from annotations,
        not from intent action results (which lack these fields).
        """
        target = {"content": "## Test Section\n\n返回400，提示用户名不能为空\n\n返回401，提示未认证"}
        annotations = [
            {"line_number": 134, "selected_text": "返回400", "review_comment": "所有接口返回200"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        # 应包含原始批注的实际字段 / Should contain actual annotation fields
        assert "返回400" in result
        assert "所有接口返回200" in result
        assert "Line ~134" in result

    def should_filter_annotations_not_in_section(self):
        """应过滤掉 selected_text 不在 section content 中的批注。

        Should filter out annotations whose selected_text does not appear
        in the target section's content.
        """
        target = {"content": "## Section A\n\nSome content here."}
        annotations = [
            {"line_number": 1, "selected_text": "Other section text", "review_comment": "Change X"},
            {"line_number": 2, "selected_text": "Some content", "review_comment": "Change Y"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        # 只应包含匹配的批注 / Should only include matching annotation
        assert "Change Y" in result
        assert "Change X" not in result

    def should_skip_annotations_with_empty_selected_text(self):
        """应跳过 selected_text 为空的批注。

        Should skip annotations that have empty selected_text.
        """
        target = {"content": "Some content."}
        annotations = [
            {"line_number": 1, "selected_text": "", "review_comment": "Empty selection"},
            {"line_number": 2, "selected_text": "Some content", "review_comment": "Valid"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        assert "Valid" in result
        assert "Empty selection" not in result

    def should_return_empty_string_when_no_matching_annotations(self):
        """当无批注匹配 section 时，应返回空字符串。

        Should return empty string when no annotations match the section.
        """
        target = {"content": "## Section A\n\nOnly this content."}
        annotations = [
            {"line_number": 1, "selected_text": "Non-existent text", "review_comment": "N/A"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        assert result == ""

    def should_use_intent_actions_and_produce_empty_output(self):
        """回归测试：传入意图分析结果（无 selected_text）应产生空输出。

        Regression test: passing intent actions (which lack selected_text)
        should produce empty output. This documents the bug we fixed.
        """
        target = {"content": "## Test Section\n\n返回400，提示用户名不能为空"}
        # 模拟 Phase 1 意图分析结果 / Simulate Phase 1 intent analysis results
        intent_actions = [
            {"section_key": "api_Test", "action": "update", "reasoning": "需要修改返回码"},
        ]

        result = _build_apply_user_prompt(target, intent_actions)

        # 意图分析结果不含 selected_text 和 review_comment，应返回空 / Empty since no matching fields
        assert result == ""


# ---------------------------------------------------------------------------
# TestGlobalAnnotationMapping / 全局批注映射测试
# ---------------------------------------------------------------------------


class TestGlobalAnnotationMapping:
    """Tests for _map_annotations_to_sections() __global__ handling."""

    def should_map_to_global_when_selected_text_in_global(self):
        """当 selected_text 在 global 内容中时，应映射到 __global__ 键。

        When selected_text is found in the global content, should map to __global__.
        """
        sections = {
            "global": "## 1. Business Understanding\n\nThis is global content with special-text.",
            "sections": [
                {"key": "api_Test", "type": "api_group", "name": "Test", "content": "API section content"},
            ],
        }
        annotations = [
            {"line_number": 1, "selected_text": "special-text", "review_comment": "Fix global"},
        ]

        mapping = _map_annotations_to_sections(sections, annotations)

        assert "__global__" in mapping
        assert len(mapping["__global__"]) == 1
        assert mapping["__global__"][0]["review_comment"] == "Fix global"

    def should_map_to_both_global_and_sections(self):
        """应同时支持映射到 global 和普通 section 的批注。

        Should handle annotations mapping to both __global__ and regular sections.
        """
        sections = {
            "global": "## 1. Overview\n\nGlobal text with keyword-A.",
            "sections": [
                {"key": "api_Test", "type": "api_group", "name": "Test", "content": "API content with keyword-B."},
            ],
        }
        annotations = [
            {"line_number": 1, "selected_text": "keyword-A", "review_comment": "Fix global"},
            {"line_number": 2, "selected_text": "keyword-B", "review_comment": "Fix api"},
        ]

        mapping = _map_annotations_to_sections(sections, annotations)

        assert "__global__" in mapping
        assert len(mapping["__global__"]) == 1
        assert mapping["__global__"][0]["review_comment"] == "Fix global"
        assert "api_Test" in mapping
        assert len(mapping["api_Test"]) == 1
        assert mapping["api_Test"][0]["review_comment"] == "Fix api"

    def should_match_global_before_sections(self):
        """当 selected_text 同时在 global 和 section 中出现时，应优先映射到 global。

        When selected_text appears in both global and a section, should map to
        __global__ first (global is checked first).
        """
        sections = {
            "global": "## 1. Overview\n\ncommon-text appears here first.",
            "sections": [
                {"key": "api_Test", "type": "api_group", "name": "Test", "content": "API content with common-text too."},
            ],
        }
        annotations = [
            {"line_number": 1, "selected_text": "common-text", "review_comment": "Change global"},
        ]

        mapping = _map_annotations_to_sections(sections, annotations)

        # global 先检查，应优先匹配 / Global checked first, takes priority
        assert "__global__" in mapping
        assert "api_Test" not in mapping
