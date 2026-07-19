"""Tests for review annotation chunk-level revision flow.

测试批注修订 Chunk 级操作: 批注映射、意图分析、动作绑定、chunk 修复。
Covers annotation mapping, intent analysis binding, chunk action execution,
and section parsing utilities.
"""

import pytest

from graph.nodes.review import (
    _detect_section_level,
    _parse_plan_to_sections,
    _scan_headings,
)
from graph.nodes.review_annotation import (
    _augment_guidance,
    _bind_actions_to_batch,
    _consolidate_annotations,
    _find_flow_by_chunk_id,
    _find_group_by_chunk_id,
    _map_annotations_to_sections,
    _validate_intent_actions,
)


# ============================================================================
# TestMapAnnotations — 批注映射 / Annotation mapping
# ============================================================================


class TestMapAnnotations:
    """Tests for _map_annotations_to_sections()."""

    def should_map_to_global_when_selected_text_in_global(self):
        sections = {
            "business_understanding": "## 1. Business Understanding\n\nThis is global content with special-text.",
            "single_api": [
                {"key": "api_Test", "type": "api", "name": "Test", "section": "single_api", "content": "API section content"},
            ],
            "biz_flows": [],
        }
        annotations = [
            {"line_number": 1, "selected_text": "special-text", "review_comment": "Fix global"},
        ]
        mapping = _map_annotations_to_sections(sections, annotations)
        assert "__global__" in mapping
        assert mapping["__global__"][0]["review_comment"] == "Fix global"

    def should_map_to_both_global_and_sections(self):
        sections = {
            "business_understanding": "## 1. Overview\n\nGlobal text with keyword-A.",
            "single_api": [
                {"key": "api_Test", "type": "api", "name": "Test", "section": "single_api", "content": "API content with keyword-B."},
            ],
            "biz_flows": [],
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
            "business_understanding": "## 1. Overview\n\ncommon-text appears here first.",
            "single_api": [
                {"key": "api_Test", "type": "api", "name": "Test", "section": "single_api", "content": "API content with common-text too."},
            ],
            "biz_flows": [],
        }
        annotations = [
            {"line_number": 1, "selected_text": "common-text", "review_comment": "Change global"},
        ]
        mapping = _map_annotations_to_sections(sections, annotations)
        assert "__global__" in mapping
        assert "api_Test" not in mapping

    def should_map_by_line_number_when_selected_text_missing(self):
        plan_md = "## 1. Overview\n\n## 2. Points\n\n### 2.1 Login\n\nrow content\n"
        sections = {
            "business_understanding": "## 1. Overview",
            "single_api": [
                {"key": "api_all", "type": "api", "name": "All",
                 "section": "single_api",
                 "content": "## 2. Points\n\n### 2.1 Login\n\nrow content"},
            ],
            "biz_flows": [],
        }
        annotations = [
            {"line_number": 5, "selected_text": "DRIFTED-TEXT", "review_comment": "fix"},
        ]
        mapping = _map_annotations_to_sections(sections, annotations, plan_md)
        assert "api_all" in mapping
        assert mapping["api_all"][0]["review_comment"] == "fix"


# ============================================================================
# TestBindActions — 动作绑定 (权威回填 section_key) / Action binding
# ============================================================================


def _make_batch(key: str, comments):
    """构造单分块 batch / Build a single-section batch."""
    return [{
        "section": {"key": key, "type": "api", "name": key, "content": ""},
        "annotations": [{"selected_text": "", "review_comment": c} for c in comments],
    }]


class TestBindActions:
    """Tests for _bind_actions_to_batch()."""

    def should_bind_actions_by_batch_order(self):
        batch = _make_batch("api_A", ["c1", "c2"])
        actions = [
            {"section_key": "api_A", "action": "fix"},
            {"section_key": "api_A", "action": "delete_chunk"},
        ]
        _bind_actions_to_batch(actions, batch)
        assert actions[0]["annotation"]["review_comment"] == "c1"
        assert actions[1]["annotation"]["review_comment"] == "c2"

    def should_override_wrong_section_key(self):
        batch = _make_batch("api_All Interfaces", ["del", "mod"])
        actions = [
            {"section_key": "api_all_interfaces", "action": "delete_chunk"},
            {"section_key": "All Interfaces", "action": "fix"},
        ]
        _bind_actions_to_batch(actions, batch)
        assert all(a["section_key"] == "api_All Interfaces" for a in actions)
        assert actions[0]["annotation"]["review_comment"] == "del"
        assert actions[1]["annotation"]["review_comment"] == "mod"

    def should_span_multiple_sections_in_order(self):
        batch = [
            {"section": {"key": "api_A", "type": "api", "name": "A", "content": ""},
             "annotations": [{"review_comment": "a1"}]},
            {"section": {"key": "api_B", "type": "api", "name": "B", "content": ""},
             "annotations": [{"review_comment": "b1"}, {"review_comment": "b2"}]},
        ]
        actions = [
            {"section_key": "?", "action": "delete_chunk"},
            {"section_key": "?", "action": "fix"},
            {"section_key": "?", "action": "fix"},
        ]
        _bind_actions_to_batch(actions, batch)
        assert actions[0]["section_key"] == "api_A"
        assert actions[0]["annotation"]["review_comment"] == "a1"
        assert actions[1]["section_key"] == "api_B"
        assert actions[1]["annotation"]["review_comment"] == "b1"
        assert actions[2]["section_key"] == "api_B"
        assert actions[2]["annotation"]["review_comment"] == "b2"

    def should_set_none_for_extra_actions(self):
        batch = _make_batch("api_A", ["only"])
        actions = [
            {"section_key": "api_A", "action": "fix"},
            {"section_key": "api_A", "action": "fix"},
        ]
        _bind_actions_to_batch(actions, batch)
        assert actions[0]["annotation"]["review_comment"] == "only"
        assert actions[1]["annotation"] is None


# ============================================================================
# TestValidateIntentActions — 意图动作校验 / Intent action validation
# ============================================================================


class TestValidateIntentActions:
    """Tests for _validate_intent_actions() with new chunk-level actions."""

    def should_error_on_count_mismatch(self):
        actions = [{"section_key": "api_A", "action": "delete_chunk"}]
        errors = _validate_intent_actions(actions, expected_count=2)
        assert any("Expected 2" in e for e in errors)

    def should_pass_when_count_matches(self):
        actions = [
            {"section_key": "api_A", "action": "delete_chunk"},
            {"section_key": "api_A", "action": "fix"},
        ]
        assert _validate_intent_actions(actions, expected_count=2) == []

    def should_skip_count_check_when_expected_negative(self):
        actions = [{"section_key": "api_A", "action": "delete_chunk"}]
        assert _validate_intent_actions(actions) == []

    def should_error_on_invalid_action(self):
        actions = [{"section_key": "api_A", "action": "frobnicate"}]
        assert _validate_intent_actions(actions, expected_count=1)

    def should_error_on_add_chunk_without_section(self):
        """add_chunk 缺少 section 字段应报错 / add_chunk without section should error."""
        actions = [{"section_key": "api_new", "action": "add_chunk"}]
        errors = _validate_intent_actions(actions, expected_count=1)
        assert any("section" in e for e in errors)

    def should_pass_valid_add_chunk_with_section(self):
        """合法的 add_chunk + section 应通过 / Valid add_chunk with section should pass."""
        actions = [{"section_key": "api_new", "action": "add_chunk", "section": "single_api"}]
        assert _validate_intent_actions(actions, expected_count=1) == []

    def should_accept_all_new_action_values(self):
        actions = [
            {"section_key": "k1", "action": "noop"},
            {"section_key": "k2", "action": "fix"},
            {"section_key": "k3", "action": "delete_chunk"},
            {"section_key": "k4", "action": "add_chunk", "section": "single_api"},
        ]
        assert _validate_intent_actions(actions, expected_count=4) == []


# ============================================================================
# TestConsolidateAnnotations — 合并批注 / Consolidate annotations
# ============================================================================


class TestConsolidateAnnotations:
    """Tests for _consolidate_annotations()."""

    def should_combine_multiple_annotations(self):
        annots = [
            {"selected_text": "text-A", "review_comment": "Change A"},
            {"selected_text": "text-B", "review_comment": "Change B"},
        ]
        result = _consolidate_annotations(annots)
        assert "Change A" in result
        assert "Change B" in result
        assert "text-A" in result
        assert "text-B" in result

    def should_handle_empty_annotation_list(self):
        assert _consolidate_annotations([]) == ""

    def should_skip_none_annotations(self):
        annots = [None, {"selected_text": "text", "review_comment": "Valid"}]
        result = _consolidate_annotations(annots)
        assert "Valid" in result

    def should_handle_missing_selected_text(self):
        annots = [{"review_comment": "Only comment"}]
        result = _consolidate_annotations(annots)
        assert "Only comment" in result


# ============================================================================
# TestFindByChunkId — chunk_id 查找 / Find by chunk_id
# ============================================================================


class TestFindByChunkId:
    """Tests for _find_flow_by_chunk_id() and _find_group_by_chunk_id()."""

    def should_find_flow_by_chunk_id(self):
        outline = {
            "biz_flows": [
                {"chunk_id": "user_register", "name": "User Register"},
            ],
        }
        flow = _find_flow_by_chunk_id(outline, "biz_user_register")
        assert flow is not None
        assert flow["name"] == "User Register"

    def should_find_group_by_chunk_id(self):
        outline = {
            "api_groups": [
                {"chunk_id": "auth", "group_name": "Auth"},
            ],
        }
        group = _find_group_by_chunk_id(outline, "api_auth")
        assert group is not None
        assert group["group_name"] == "Auth"

    def should_return_none_for_missing_flow(self):
        assert _find_flow_by_chunk_id({}, "biz_nonexistent") is None

    def should_return_none_for_missing_group(self):
        assert _find_group_by_chunk_id({"api_groups": []}, "api_nonexistent") is None


# ============================================================================
# TestAugmentGuidance — 追加修订指导 / Augment user guidance
# ============================================================================


class TestAugmentGuidance:
    """Tests for _augment_guidance()."""

    def should_append_fix_instructions(self):
        result = _augment_guidance("original guidance", "Fix the auth tests")
        assert "original guidance" in result
        assert "Fix the auth tests" in result
        assert "Revision Instructions" in result

    def should_handle_empty_fix_text(self):
        result = _augment_guidance("original", "")
        assert result == "original"

    def should_handle_none_user_guidance(self):
        result = _augment_guidance("", "fix text")
        assert "(none)" in result
        assert "fix text" in result


# ============================================================================
# TestScanHeadings — 动态标题识别 / Dynamic heading detection
# ============================================================================


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


# ============================================================================
# TestDetectSectionLevel — 主分段级别检测 / Section level detection
# ============================================================================


class TestDetectSectionLevel:
    """Tests for _detect_section_level() — heading-level heuristic."""

    def should_detect_level_2_for_original_h2_format(self):
        plan = "## 1. Overview\n\ntext\n\n## 2. API Points\n\ntext"
        assert _detect_section_level(plan) == 2

    def should_detect_level_3_for_revised_h3_format(self):
        plan = (
            "## Revised Plan\n\n"
            "### 1. Business Understanding\n\ntext\n\n"
            "### 2. Single Interface\n\ntext\n\n"
            "### 3. Business Flow\n\ntext"
        )
        assert _detect_section_level(plan) == 3

    def should_return_shallowest_repeated_level(self):
        plan = (
            "## A\n\ntext\n\n## B\n\ntext\n\n"
            "### C\n\ntext\n\n### D\n\ntext"
        )
        assert _detect_section_level(plan) == 2

    def should_return_min_when_all_levels_unique(self):
        plan = "# Title\n\n## Section\n\n### Sub\n\n#### Subsub"
        assert _detect_section_level(plan) == 1

    def should_return_default_for_no_headings(self):
        assert _detect_section_level("Plain text with no headings.") == 2

    def should_skip_level_appearing_once_when_deeper_repeats(self):
        plan = "# Solo Title\n\n## 1. A\n\ntext\n\n## 2. B\n\ntext"
        assert _detect_section_level(plan) == 2


# ============================================================================
# TestParsePlanToSectionsFlexible — 灵活解析 / Flexible section parsing
# ============================================================================


class TestParsePlanToSectionsFlexible:
    """Tests for _parse_plan_to_sections() — heading-level adaptive parsing."""

    OUTLINE_BASIC = {
        "api_groups": [
            {"group_name": "Auth"},
            {"group_name": "Products"},
        ],
        "biz_flows": [
            {"name": "Purchase Flow"},
        ],
    }

    def should_split_by_detected_h2_level(self):
        plan = (
            "## 1. Business Understanding\n\nContext text\n\n"
            "## 2. Single Interface Test Points\n\n"
            "### Auth\n\nTest case 1\n\n"
            "### Products\n\nTest case 2\n\n"
            "## 3. Business Flow Testing\n\n"
            "### Purchase Flow\n\nFlow test\n\n"
            "## 4. Flowchart\n\n```mermaid\ngraph\n```"
        )
        result = _parse_plan_to_sections(plan, self.OUTLINE_BASIC)
        assert result["business_understanding"], "business_understanding should not be empty"
        assert len(result["single_api"]) + len(result["biz_flows"]) >= 2

    def should_split_by_detected_h3_level(self):
        plan = (
            "## Revised Plan\n\n"
            "### 1. Business Understanding\n\ncontext\n\n"
            "### 2. Single Interface\n\n"
            "#### Auth\n\ntest case\n\n"
            "### 3. Business Flow\n\nflow\n\n"
            "### 4. Flowchart\n\nmermaid"
        )
        result = _parse_plan_to_sections(plan, self.OUTLINE_BASIC)
        assert result["business_understanding"], "business_understanding should not be empty"
        assert len(result["single_api"]) + len(result["biz_flows"]) >= 2

    def should_classify_by_en_keywords(self):
        plan = (
            "## 1. Business Understanding\n\ncontext\n\n"
            "## 2. Single Interface Test Points\n\n"
            "### Auth\n\ncase\n\n"
            "## 3. Business Flow Testing\n\nflow\n\n"
            "## 4. Flowchart\n\nmermaid"
        )
        result = _parse_plan_to_sections(plan, self.OUTLINE_BASIC)
        api_sections = result["single_api"]
        biz_sections = result["biz_flows"]
        assert len(api_sections) >= 1
        assert len(biz_sections) >= 1

    def should_handle_empty_plan(self):
        result = _parse_plan_to_sections("", None)
        assert result == {"business_understanding": "", "single_api": [], "biz_flows": []}

    def should_handle_plain_text_without_headings(self):
        result = _parse_plan_to_sections("Just plain text here.", None)
        assert result["single_api"] == []
        assert result["biz_flows"] == []
        assert "plain text" in result["business_understanding"]
