"""Tests for review annotation three-phase revision flow.

测试批注修订三阶段流程中的关键函数。
Covers dynamic block location, precise deletion, block-level splice,
annotation binding, and section mapping.
"""

import pytest

from graph.nodes.review_annotation import (
    _apply_actions_to_section,
    _bind_actions_to_batch,
    _build_apply_user_prompt,
    _enclosing_block,
    _locate_anchor,
    _map_annotations_to_sections,
    _phase1_intent_analysis,
    _remove_annotation_target,
    _scan_headings,
    _validate_intent_actions,
)


# ---------------------------------------------------------------------------
# 测试桩 / Test stubs
# ---------------------------------------------------------------------------


class _FakeAgent:
    """伪 LLM agent，返回固定响应 / Fake LLM agent returning a canned response."""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def call_llm(self, prompt: str, system: str) -> str:
        self.calls.append((prompt, system))
        return self.response


class _TokenCounter:
    """伪 token 计数器 / Trivial token counter stub."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class _FakeIntentAgent:
    """伪意图 agent, 返回预置动作 (可含错误 section_key) / Fake intent agent.

    用于验证 Phase 1 绑定在 LLM 回传错误 section_key 时仍能纠正并绑定。
    Returns canned intent actions to verify binding corrects wrong section_key.
    """

    def __init__(self, actions):
        self._actions = actions
        self.calls = 0

    def reset_steps(self):
        pass

    def call_llm_json(self, prompt: str, system: str):
        self.calls += 1
        return {"actions": self._actions}


# ---------------------------------------------------------------------------
# TestBuildApplyUserPrompt / 构建内容生成 USER prompt 测试
# ---------------------------------------------------------------------------


class TestBuildApplyUserPrompt:
    """Tests for _build_apply_user_prompt()."""

    def should_use_annotations_not_intent_actions(self):
        """应使用原始批注数据 / Should read selected_text and review_comment from annotations."""
        target = {"content": "## Test Section\n\n返回400，提示用户名不能为空\n\n返回401，提示未认证"}
        annotations = [
            {"line_number": 134, "selected_text": "返回400", "review_comment": "所有接口返回200"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        assert "返回400" in result
        assert "所有接口返回200" in result
        assert "Line ~134" in result

    def should_filter_annotations_not_in_section(self):
        """应过滤掉 selected_text 不在 content 中的批注 / Filter out non-matching annotations."""
        target = {"content": "## Section A\n\nSome content here."}
        annotations = [
            {"line_number": 1, "selected_text": "Other section text", "review_comment": "Change X"},
            {"line_number": 2, "selected_text": "Some content", "review_comment": "Change Y"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        assert "Change Y" in result
        assert "Change X" not in result

    def should_skip_annotations_with_empty_selected_text(self):
        """应跳过 selected_text 为空的批注 / Skip annotations with empty selected_text."""
        target = {"content": "Some content."}
        annotations = [
            {"line_number": 1, "selected_text": "", "review_comment": "Empty selection"},
            {"line_number": 2, "selected_text": "Some content", "review_comment": "Valid"},
        ]

        result = _build_apply_user_prompt(target, annotations)

        assert "Valid" in result
        assert "Empty selection" not in result

    def should_return_empty_string_when_no_matching_annotations(self):
        """无匹配批注时应返回空字符串 / Empty string when nothing matches."""
        target = {"content": "## Section A\n\nOnly this content."}
        annotations = [
            {"line_number": 1, "selected_text": "Non-existent text", "review_comment": "N/A"},
        ]

        assert _build_apply_user_prompt(target, annotations) == ""

    def should_use_intent_actions_and_produce_empty_output(self):
        """回归: 意图动作 (无 selected_text) 应产生空输出 / Intent actions produce empty output."""
        target = {"content": "## Test Section\n\n返回400，提示用户名不能为空"}
        intent_actions = [
            {"section_key": "api_Test", "action": "update", "reasoning": "需要修改返回码"},
        ]

        assert _build_apply_user_prompt(target, intent_actions) == ""


# ---------------------------------------------------------------------------
# TestGlobalAnnotationMapping / 批注映射测试
# ---------------------------------------------------------------------------


class TestGlobalAnnotationMapping:
    """Tests for _map_annotations_to_sections()."""

    def should_map_to_global_when_selected_text_in_global(self):
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

        assert mapping["__global__"][0]["review_comment"] == "Fix global"
        assert mapping["api_Test"][0]["review_comment"] == "Fix api"

    def should_match_global_before_sections(self):
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

        assert "__global__" in mapping
        assert "api_Test" not in mapping

    def should_map_by_line_number_when_selected_text_missing(self):
        """selected_text 匹配失败但 line_number 落点有效时应映射, 不丢弃。

        When selected_text doesn't match but line_number falls in a section's
        line range, the annotation is still mapped (not silently dropped).
        """
        # global 占 1-2 行, api section 从第 4 行开始
        plan_md = "## 1. Overview\n\n## 2. Points\n\n### 2.1 Login\n\nrow content\n"
        sections = {
            "global": "## 1. Overview",
            "sections": [
                {"key": "api_all", "type": "api_group", "name": "All",
                 "content": "## 2. Points\n\n### 2.1 Login\n\nrow content"},
            ],
        }
        # selected_text 已漂移无法匹配, 但 line_number=5 落在 api section 内
        annotations = [
            {"line_number": 5, "selected_text": "DRIFTED-TEXT", "review_comment": "fix"},
        ]

        mapping = _map_annotations_to_sections(sections, annotations, plan_md)

        assert "api_all" in mapping
        assert mapping["api_all"][0]["review_comment"] == "fix"


# ---------------------------------------------------------------------------
# TestScanHeadings / TestEnclosingBlock — 动态标题识别
# ---------------------------------------------------------------------------


class TestScanHeadings:
    """Tests for _scan_headings() — heading levels detected dynamically."""

    def should_detect_all_heading_levels(self):
        content = "## H2\n\n### H3\n\ntext\n\n#### H4\n"
        levels = [lvl for _, lvl, _ in _scan_headings(content)]
        assert levels == [2, 3, 4]

    def should_ignore_non_heading_hashes(self):
        content = "text #notheading\n\n### Real\n"
        headings = _scan_headings(content)
        assert len(headings) == 1
        assert headings[0][1] == 3


class TestEnclosingBlock:
    """Tests for _enclosing_block() — bounds by same-or-higher heading."""

    def should_bound_by_same_level_heading(self):
        content = "### A\n\naaa\n\n### B\n\nbbb\n"
        anchor = content.index("aaa")
        start, end = _enclosing_block(content, anchor)
        block = content[start:end]
        assert "### A" in block and "aaa" in block
        assert "### B" not in block

    def should_return_deepest_nested_block(self):
        content = "### A\n\n#### A1\n\naaa\n\n#### A2\n\nbbb\n"
        anchor = content.index("aaa")
        start, end = _enclosing_block(content, anchor)
        block = content[start:end]
        assert block.strip().startswith("#### A1")
        assert "#### A2" not in block
        assert "bbb" not in block

    def should_return_whole_content_when_no_headings(self):
        content = "just some text\nwith no headings\n"
        assert _enclosing_block(content, 3) == (0, len(content))

    def should_return_prefix_when_anchor_before_first_heading(self):
        content = "intro text\n\n### A\n\naaa\n"
        anchor = content.index("intro")
        start, end = _enclosing_block(content, anchor)
        assert start == 0
        assert content[end:].startswith("### A")


# ---------------------------------------------------------------------------
# TestLocateAnchor / 行号消歧
# ---------------------------------------------------------------------------


class TestLocateAnchor:
    """Tests for _locate_anchor()."""

    def should_disambiguate_duplicate_by_line_number(self):
        content = (
            "### 2.1 A\n\n#### 负向用例\n\nrowA\n\n"
            "### 2.2 B\n\n#### 负向用例\n\nrowB\n"
        )
        first = content.index("负向用例")
        second = content.index("负向用例", first + 1)
        # 第二个 "负向用例" 位于第 9 行 / second occurrence is on line 9
        ann = {"line_number": 9, "selected_text": "负向用例"}

        anchor = _locate_anchor(content, ann, base_line=1)

        assert anchor == second
        assert anchor != first

    def should_fallback_to_selected_text_without_base_line(self):
        content = "### A\n\nunique-marker here\n"
        ann = {"line_number": 999, "selected_text": "unique-marker"}
        anchor = _locate_anchor(content, ann, base_line=None)
        assert anchor == content.index("unique-marker")

    def should_return_minus_one_when_unlocatable(self):
        content = "### A\n\ntext\n"
        ann = {"line_number": 1, "selected_text": "not-present"}
        assert _locate_anchor(content, ann, base_line=None) == -1


# ---------------------------------------------------------------------------
# TestRemoveAnnotationTarget / 精确删除
# ---------------------------------------------------------------------------


class TestRemoveAnnotationTarget:
    """Tests for _remove_annotation_target()."""

    def should_remove_only_matched_table_row(self):
        content = (
            "#### 负向用例\n\n"
            "| 用例 | 说明 |\n| --- | --- |\n"
            "| 密码错误 | 返回401 |\n| 用户被禁用 | 返回403 |\n"
        )
        ann = {"line_number": 0, "selected_text": "用户被禁用"}

        result = _remove_annotation_target(content, ann, base_line=None)

        assert result is not None
        assert "用户被禁用" not in result
        assert "密码错误" in result
        assert "| 用例 | 说明 |" in result  # 表头保留 / header kept

    def should_remove_enclosing_heading_block(self):
        content = "#### 场景1\n\n步骤1\n\n#### 场景2\n\n步骤2\n"
        ann = {"line_number": 0, "selected_text": "场景2"}

        result = _remove_annotation_target(content, ann, base_line=None)

        assert result is not None
        assert "场景2" not in result
        assert "步骤2" not in result
        assert "场景1" in result
        assert "步骤1" in result

    def should_return_none_when_anchor_not_found(self):
        content = "#### 场景1\n\n步骤1\n"
        ann = {"line_number": 0, "selected_text": "不存在的文本"}
        assert _remove_annotation_target(content, ann, base_line=None) is None


# ---------------------------------------------------------------------------
# TestApplyActionsToSection / 块级 splice (只替换目标块)
# ---------------------------------------------------------------------------


class TestApplyActionsToSection:
    """Tests for _apply_actions_to_section() — only the target block is replaced."""

    def should_splice_only_target_block(self):
        content = (
            "## 2. 单接口测试点\n\n"
            "### 2.1 创建订单\n\n正向用例A\n\n"
            "### 2.2 获取订单\n\n正向用例B\n"
        )
        target = {"key": "api_all", "name": "All", "content": content}
        acts = [{
            "section_key": "api_all", "action": "add",
            "annotation": {"line_number": 0, "selected_text": "获取订单",
                           "review_comment": "新增一条负向用例"},
        }]
        agent = _FakeAgent("### 2.2 获取订单\n\n正向用例B\n\n负向用例C")

        _apply_actions_to_section(target, acts, None, _TokenCounter(), agent)

        assert "负向用例C" in target["content"]
        # 其他块保持不动 / other blocks untouched
        assert "### 2.1 创建订单" in target["content"]
        assert "正向用例A" in target["content"]
        assert "## 2. 单接口测试点" in target["content"]
        assert len(agent.calls) == 1

    def should_fallback_to_whole_section_when_unlocatable(self):
        content = "### 2.1 创建订单\n\n正向用例A\n"
        target = {"key": "api_all", "name": "All", "content": content}
        acts = [{
            "section_key": "api_all", "action": "update",
            "annotation": {"line_number": 0, "selected_text": "无法定位",
                           "review_comment": "改点东西"},
        }]
        agent = _FakeAgent("### 2.1 创建订单\n\n正向用例A 已更新")

        _apply_actions_to_section(target, acts, None, _TokenCounter(), agent)

        assert "已更新" in target["content"]
        assert len(agent.calls) == 1


# ---------------------------------------------------------------------------
# TestBindActions / 按批次顺序绑定 (权威回填 section_key)
# ---------------------------------------------------------------------------


def _make_batch(key: str, comments):
    """构造单分块 batch / Build a single-section batch."""
    return [{
        "section": {"key": key, "type": "api_group", "name": key, "content": ""},
        "annotations": [{"selected_text": "", "review_comment": c} for c in comments],
    }]


class TestBindActions:
    """Tests for _bind_actions_to_batch()."""

    def should_bind_actions_by_batch_order(self):
        batch = _make_batch("api_A", ["c1", "c2"])
        actions = [
            {"section_key": "api_A", "action": "update"},
            {"section_key": "api_A", "action": "delete"},
        ]

        _bind_actions_to_batch(actions, batch)

        assert actions[0]["annotation"]["review_comment"] == "c1"
        assert actions[1]["annotation"]["review_comment"] == "c2"

    def should_override_wrong_section_key(self):
        """回归本 bug: LLM 回传归一化/错误的 section_key 时仍纠正回权威键并正确绑定。

        Regression: even when the LLM returns a wrong/normalized section_key,
        the action is rebound to the authoritative key and correct annotation.
        """
        batch = _make_batch("api_All Interfaces", ["del", "mod"])
        actions = [
            {"section_key": "api_all_interfaces", "action": "delete"},
            {"section_key": "All Interfaces", "action": "update"},
        ]

        _bind_actions_to_batch(actions, batch)

        assert all(a["section_key"] == "api_All Interfaces" for a in actions)
        assert actions[0]["annotation"]["review_comment"] == "del"
        assert actions[1]["annotation"]["review_comment"] == "mod"

    def should_span_multiple_sections_in_order(self):
        batch = [
            {"section": {"key": "api_A", "type": "api_group", "name": "A", "content": ""},
             "annotations": [{"review_comment": "a1"}]},
            {"section": {"key": "api_B", "type": "api_group", "name": "B", "content": ""},
             "annotations": [{"review_comment": "b1"}, {"review_comment": "b2"}]},
        ]
        actions = [
            {"section_key": "?", "action": "delete"},
            {"section_key": "?", "action": "update"},
            {"section_key": "?", "action": "add"},
        ]

        _bind_actions_to_batch(actions, batch)

        assert actions[0]["section_key"] == "api_A"
        assert actions[0]["annotation"]["review_comment"] == "a1"
        assert actions[1]["section_key"] == "api_B"
        assert actions[1]["annotation"]["review_comment"] == "b1"
        assert actions[2]["section_key"] == "api_B"
        assert actions[2]["annotation"]["review_comment"] == "b2"

    def should_set_none_for_extra_actions(self):
        """动作多于批注时, 多出的置 None / Extra actions get annotation=None."""
        batch = _make_batch("api_A", ["only"])
        actions = [
            {"section_key": "api_A", "action": "update"},
            {"section_key": "api_A", "action": "add"},
        ]

        _bind_actions_to_batch(actions, batch)

        assert actions[0]["annotation"]["review_comment"] == "only"
        assert actions[1]["annotation"] is None


# ---------------------------------------------------------------------------
# TestValidateIntentActions / 意图动作校验 (含条数一致性)
# ---------------------------------------------------------------------------


class TestValidateIntentActions:
    """Tests for _validate_intent_actions()."""

    def should_error_on_count_mismatch(self):
        actions = [{"section_key": "api_A", "action": "delete"}]
        errors = _validate_intent_actions(actions, expected_count=2)
        assert any("Expected 2" in e for e in errors)

    def should_pass_when_count_matches(self):
        actions = [
            {"section_key": "api_A", "action": "delete"},
            {"section_key": "api_A", "action": "update"},
        ]
        assert _validate_intent_actions(actions, expected_count=2) == []

    def should_skip_count_check_when_expected_negative(self):
        actions = [{"section_key": "api_A", "action": "delete"}]
        assert _validate_intent_actions(actions) == []

    def should_error_on_invalid_action(self):
        actions = [{"section_key": "api_A", "action": "frobnicate"}]
        assert _validate_intent_actions(actions, expected_count=1)


# ---------------------------------------------------------------------------
# TestPhase1Binding / Phase 1 端到端绑定 (回传错误 key 也能生效)
# ---------------------------------------------------------------------------


class TestPhase1Binding:
    """Tests for _phase1_intent_analysis() end-to-end binding."""

    def should_bind_even_when_llm_returns_wrong_section_key(self, monkeypatch):
        """回归: LLM 回传错误 section_key 时, Phase 1 仍产出可被 Phase 2/3 执行的动作。

        Regression for the "instant re-review, zero change" bug: with a wrong
        section_key from the LLM, every returned action must still carry a
        non-None annotation and the corrected authoritative section_key.
        """
        import types

        from graph.nodes import helpers as _h
        import graph.nodes.review_annotation as ra

        sections = {
            "global": "## 1. Overview\n\nglobal text",
            "sections": [
                {"key": "api_All Interfaces", "type": "api_group",
                 "name": "All Interfaces",
                 "content": "## 2. Points\n\n### A\n\ncase-x\n\n### B\n\ncase-y"},
            ],
        }
        section_annotations = {
            "api_All Interfaces": [
                {"line_number": 3, "selected_text": "case-x", "review_comment": "删除"},
                {"line_number": 5, "selected_text": "case-y", "review_comment": "修改"},
            ],
        }
        # LLM 回传归一化后的错误 section_key / LLM returns wrong normalized keys
        wrong_actions = [
            {"section_key": "api_all_interfaces", "action": "delete", "reasoning": "d"},
            {"section_key": "All Interfaces", "action": "update", "reasoning": "u"},
        ]
        monkeypatch.setattr(_h, "_settings", types.SimpleNamespace(
            llm_context_window=8192, llm_max_output_tokens=2048, max_retries=1,
        ))
        monkeypatch.setattr(
            ra, "_make_intent_agent", lambda state: _FakeIntentAgent(wrong_actions)
        )

        actions = ra._phase1_intent_analysis(
            sections, section_annotations, _TokenCounter(), {}
        )

        assert len(actions) == 2
        assert all(a["section_key"] == "api_All Interfaces" for a in actions)
        assert actions[0]["action"] == "delete"
        assert actions[0]["annotation"]["review_comment"] == "删除"
        assert actions[1]["action"] == "update"
        assert actions[1]["annotation"]["review_comment"] == "修改"

